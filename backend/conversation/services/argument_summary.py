from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.db import close_old_connections
from django.db import transaction
from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm

logger = logging.getLogger(__name__)

_STATUS_PENDING = "pending"
_STATUS_READY = "ready"
_STATUS_FAILED = "failed"
_STATUS_EMPTY = "empty"

_MAX_WORDS = 8
_MAX_CHARS = 60
_VALID_PACKAGE_TYPES = frozenset({"argument", "counterargument"})
_VALID_EXPLANATION_TYPES = frozenset({"fact", "data", "example"})
_PACKAGE_LABELS = {"argument": "For", "counterargument": "Against"}
_EXPLANATION_LABELS = {"fact": "Fact", "data": "Data", "example": "Example"}

_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="argument-summary",
)

_in_flight_sessions: set[int] = set()
_pending_refresh_sessions: set[int] = set()
_scheduler_lock = threading.Lock()


def _speaker_label(session: ConversationSession, turn: TurnRecord) -> str:
    if turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
        profile = getattr(session.user, "userprofile", None)
        preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
        return preferred or (getattr(session.user, "name", "") or "").strip() or "You"
    agent = AgentProfile.objects.filter(session_id=session.id, agent_id=turn.speaker).only(
        "display_name",
        "agent_id",
    ).first()
    if agent is not None:
        return (agent.display_name or agent.agent_id).strip()
    return turn.speaker


def build_numbered_transcript(session: ConversationSession) -> str:
    turns = list(session.turns.order_by("turn_index", "subturn_index"))
    lines: list[str] = []
    display_turn_number = 0
    previous_turn_index: int | None = None
    for turn in turns:
        if turn.turn_index != previous_turn_index:
            display_turn_number += 1
            previous_turn_index = turn.turn_index
        speaker = _speaker_label(session, turn)
        utterance = (turn.utterance or "").strip()
        if not utterance:
            continue
        lines.append(f"Turn {display_turn_number} [{speaker}]: {utterance}")
    return "\n".join(lines)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _clamp_text(text: str, *, max_words: int = _MAX_WORDS, max_chars: int = _MAX_CHARS) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def _normalize_reason(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        text = _clamp_text(str(value.get("text") or ""))
    elif isinstance(value, str):
        text = _clamp_text(value)
    else:
        text = ""
    return {"text": text}


def _normalize_explanations(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        explanation_type = str(item.get("type") or "fact").strip().lower()
        if explanation_type not in _VALID_EXPLANATION_TYPES:
            explanation_type = "fact"
        text = _clamp_text(str(item.get("text") or ""))
        if text:
            normalized.append({"type": explanation_type, "text": text})
    return normalized[:2]


def _normalize_argument_package(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    package_type = str(item.get("type") or "argument").strip().lower()
    if package_type not in _VALID_PACKAGE_TYPES:
        package_type = "argument"
    reason = _normalize_reason(item.get("reason"))
    if not reason["text"]:
        return None
    explanations = _normalize_explanations(item.get("explanations"))
    return {
        "type": package_type,
        "reason": reason,
        "explanations": explanations,
    }


def _normalize_claim(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("claim"), dict):
        claim_text = _clamp_text(str(item["claim"].get("text") or ""))
    else:
        claim_text = _clamp_text(str(item.get("text") or ""))
    if not claim_text:
        return None

    packages_raw = item.get("arguments")
    packages: list[dict[str, Any]] = []
    if isinstance(packages_raw, list):
        for entry in packages_raw:
            package = _normalize_argument_package(entry)
            if package is not None:
                packages.append(package)
    packages = packages[:2]

    if not packages:
        return None
    return {"text": claim_text, "arguments": packages}


def _migrate_legacy_thread(thread: dict[str, Any]) -> dict[str, Any] | None:
    claim_raw = thread.get("claim")
    claim_text = ""
    if isinstance(claim_raw, dict):
        claim_text = _clamp_text(str(claim_raw.get("text") or ""))
    if not claim_text:
        return None

    packages: list[dict[str, Any]] = []
    grounds = thread.get("grounds")
    if isinstance(grounds, list):
        for ground in grounds:
            if not isinstance(ground, dict):
                continue
            reason_text = _clamp_text(str(ground.get("text") or ""))
            if not reason_text:
                continue
            explanations: list[dict[str, str]] = []
            for fact in ground.get("supporting_facts") or []:
                fact_text = _clamp_text(str(fact))
                if fact_text:
                    explanations.append({"type": "fact", "text": fact_text})
            packages.append(
                {
                    "type": "argument",
                    "reason": {"text": reason_text},
                    "explanations": explanations[:2],
                },
            )
            if len(packages) >= 2:
                break

    rebuttals = thread.get("rebuttals")
    if isinstance(rebuttals, list) and len(packages) < 2:
        for rebuttal in rebuttals:
            if not isinstance(rebuttal, dict):
                continue
            counter = rebuttal.get("counterargument")
            if not isinstance(counter, dict):
                continue
            reason_text = _clamp_text(str(counter.get("text") or ""))
            if not reason_text:
                continue
            packages.append(
                {
                    "type": "counterargument",
                    "reason": {"text": reason_text},
                    "explanations": [],
                },
            )
            break

    if not packages:
        return None
    return {"text": claim_text, "arguments": packages[:2]}


def parse_argument_summary_response(raw: str) -> dict[str, Any]:
    parsed = _extract_json_object(raw)
    claims: list[dict[str, Any]] = []

    claims_raw = parsed.get("claims")
    if isinstance(claims_raw, list):
        for item in claims_raw:
            claim = _normalize_claim(item)
            if claim is not None:
                claims.append(claim)

    if not claims:
        threads_raw = parsed.get("argument_threads")
        if isinstance(threads_raw, list):
            for thread in threads_raw:
                if not isinstance(thread, dict):
                    continue
                migrated = _migrate_legacy_thread(thread)
                if migrated is not None:
                    claims.append(migrated)

    return {"claims": claims[:2]}


def _claims_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    claims_raw = summary.get("claims")
    if isinstance(claims_raw, list) and claims_raw:
        return claims_raw
    threads_raw = summary.get("argument_threads")
    if not isinstance(threads_raw, list):
        return []
    migrated: list[dict[str, Any]] = []
    for thread in threads_raw:
        if not isinstance(thread, dict):
            continue
        claim = _migrate_legacy_thread(thread)
        if claim is not None:
            migrated.append(claim)
    return migrated


def format_argument_summary_bullets(summary: dict[str, Any]) -> str:
    if summary.get("status") != _STATUS_READY:
        return ""

    lines: list[str] = []
    for claim in _claims_from_summary(summary):
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("text") or "").strip()
        if not claim_text:
            continue
        lines.append(f"- {claim_text}")

        for package in claim.get("arguments") or []:
            if not isinstance(package, dict):
                continue
            package_type = str(package.get("type") or "argument")
            label = _PACKAGE_LABELS.get(package_type, "For")
            reason = package.get("reason") if isinstance(package.get("reason"), dict) else {}
            reason_text = str(reason.get("text") or "").strip()
            if reason_text:
                lines.append(f"  - {label}: {reason_text}")
            for explanation in package.get("explanations") or []:
                if not isinstance(explanation, dict):
                    continue
                explanation_text = str(explanation.get("text") or "").strip()
                if not explanation_text:
                    continue
                explanation_type = str(explanation.get("type") or "fact")
                type_label = _EXPLANATION_LABELS.get(explanation_type, "Fact")
                lines.append(f"    - {type_label}: {explanation_text}")

    return "\n".join(lines)


_ARGUMENT_SUMMARY_PENDING_AGENT_GUIDANCE = (
    "Argument summary is still being updated in the background. "
    "Review the discussion history and do not repeat claims, reasons, "
    "facts, data, examples, or counterarguments already stated."
)

_ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE = (
    "No structured argument summary is available yet. "
    "Avoid repeating points already made in the discussion history."
)


def get_argument_summary_bullets_for_agent(session: ConversationSession) -> str:
    session.refresh_from_db(fields=["argument_summary"])
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if not stored:
        return _ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE

    status = stored.get("status")
    if status == _STATUS_READY:
        bullets = format_argument_summary_bullets(stored)
        return bullets or _ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE
    if status == _STATUS_PENDING:
        bullets = format_argument_summary_bullets(stored)
        if bullets:
            return (
                f"{bullets}\n\n"
                "(Summary is still being refreshed; treat the bullets above as already covered.)"
            )
        return _ARGUMENT_SUMMARY_PENDING_AGENT_GUIDANCE
    return _ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE


def _previous_summary_json(session: ConversationSession) -> str:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if not stored or stored.get("status") != _STATUS_READY:
        return "(none)"
    claims = _claims_from_summary(stored)
    if not claims:
        return "(none)"
    return json.dumps({"claims": claims}, ensure_ascii=False, indent=2)


def build_argument_summary_prompt(*, session: ConversationSession) -> str:
    template = load_additional_prompt("argument_summary.txt")
    return render_prompt_template(
        template,
        topic=(session.topic or "").strip() or "General discussion",
        transcript=build_numbered_transcript(session),
        previous_summary=_previous_summary_json(session),
    )


def extract_argument_summary(
    *,
    session: ConversationSession,
    llm: Any | None = None,
) -> dict[str, Any]:
    llm = llm or get_default_chat_llm()
    prompt = build_argument_summary_prompt(session=session)
    result = llm.invoke([SystemMessage(content=prompt)])
    raw = result.content if hasattr(result, "content") else str(result)
    return parse_argument_summary_response(raw)


def _summary_payload(*, status: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"status": status}
    if data:
        payload.update(data)
    return payload


def generate_argument_summary_for_session(session: ConversationSession) -> dict[str, Any]:
    if not session.turns.exists():
        return _summary_payload(status=_STATUS_EMPTY)

    try:
        parsed = extract_argument_summary(session=session)
    except Exception:
        logger.exception("argument_summary_generation_failed", extra={"session_id": session.id})
        session.argument_summary = _summary_payload(status=_STATUS_FAILED)
        session.save(update_fields=["argument_summary", "updated_at"])
        return session.argument_summary

    if not parsed.get("claims"):
        payload = _summary_payload(status=_STATUS_EMPTY, data={"claims": []})
    else:
        payload = _summary_payload(status=_STATUS_READY, data=parsed)

    session.argument_summary = payload
    session.save(update_fields=["argument_summary", "updated_at"])
    return payload


def mark_argument_summary_pending(session: ConversationSession) -> None:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if stored and stored.get("status") == _STATUS_READY:
        return
    session.argument_summary = _summary_payload(status=_STATUS_PENDING)
    session.save(update_fields=["argument_summary", "updated_at"])


def get_argument_summary_for_session(session: ConversationSession) -> dict[str, Any]:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if stored and stored.get("status") in {_STATUS_READY, _STATUS_FAILED, _STATUS_EMPTY}:
        return stored
    if stored and stored.get("status") == _STATUS_PENDING:
        return stored
    if not session.turns.exists():
        return _summary_payload(status=_STATUS_EMPTY)
    return generate_argument_summary_for_session(session)


def _submit_background(func: Any, **kwargs: Any) -> None:
    _EXECUTOR.submit(func, **kwargs)


def _run_argument_summary_loop(*, session_id: int) -> None:
    try:
        while True:
            session = (
                ConversationSession.objects.filter(id=session_id)
                .select_related("user__userprofile")
                .first()
            )
            if session is None:
                logger.info("argument_summary_missing_session", extra={"session_id": session_id})
                break
            try:
                generate_argument_summary_for_session(session)
            except Exception:
                logger.exception(
                    "argument_summary_background_failed",
                    extra={"session_id": session_id},
                )
                ConversationSession.objects.filter(id=session_id).update(
                    argument_summary=_summary_payload(status=_STATUS_FAILED),
                )
                break

            with _scheduler_lock:
                if session_id not in _pending_refresh_sessions:
                    break
                _pending_refresh_sessions.discard(session_id)
    finally:
        with _scheduler_lock:
            _in_flight_sessions.discard(session_id)
            needs_rerun = session_id in _pending_refresh_sessions
            if needs_rerun and session_id not in _in_flight_sessions:
                _in_flight_sessions.add(session_id)
                _submit_background(_run_argument_summary_loop, session_id=session_id)
        close_old_connections()


def _enqueue_argument_summary_refresh(session_id: int) -> None:
    with _scheduler_lock:
        if session_id in _in_flight_sessions:
            _pending_refresh_sessions.add(session_id)
            return
        _in_flight_sessions.add(session_id)

    session = ConversationSession.objects.filter(id=session_id).first()
    if session is None:
        with _scheduler_lock:
            _in_flight_sessions.discard(session_id)
        return

    if not session.turns.exists():
        session.argument_summary = _summary_payload(status=_STATUS_EMPTY)
        session.save(update_fields=["argument_summary", "updated_at"])
        with _scheduler_lock:
            _in_flight_sessions.discard(session_id)
        return

    mark_argument_summary_pending(session)
    _submit_background(_run_argument_summary_loop, session_id=session_id)


def schedule_argument_summary_refresh(session: ConversationSession) -> None:
    session_id = session.id
    transaction.on_commit(lambda: _enqueue_argument_summary_refresh(session_id))


def schedule_argument_summary_refresh_for_session_id(session_id: int) -> None:
    transaction.on_commit(lambda: _enqueue_argument_summary_refresh(session_id))


schedule_argument_summary_for_session = schedule_argument_summary_refresh

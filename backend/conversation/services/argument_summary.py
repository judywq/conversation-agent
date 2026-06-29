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
from backend.conversation.services.conversation_phase import is_closing_turn as is_closing_turn_phase
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.llm_tracing import conversation_tracing_context
from backend.conversation.services.llm_tracing import invoke_chat_llm

logger = logging.getLogger(__name__)

_STATUS_PENDING = "pending"
_STATUS_READY = "ready"
_STATUS_FAILED = "failed"
_STATUS_EMPTY = "empty"

_MAX_WORDS = 15
_MAX_CHARS = 100
_MAX_REASON_WORDS = 12
_MAX_REASON_CHARS = 80
_MAX_EXPLANATION_WORDS = 10
_MAX_EXPLANATION_CHARS = 60
_MAX_SPEAKERS = 6
_VALID_EXPLANATION_TYPES = frozenset({"fact", "data", "example"})
_EXPLANATION_LABELS = {"fact": "Fact", "data": "Data", "example": "Example"}

_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="argument-summary",
)

_in_flight_sessions: set[int] = set()
_pending_refresh_sessions: set[int] = set()
_scheduler_lock = threading.Lock()


def is_closing_turn(session: ConversationSession) -> bool:
    return is_closing_turn_phase(session)


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


def _text_key(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def _normalize_explanation(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    explanation_type = str(item.get("type") or "fact").strip().lower()
    if explanation_type not in _VALID_EXPLANATION_TYPES:
        explanation_type = "fact"
    text = _clamp_text(
        str(item.get("text") or ""),
        max_words=_MAX_EXPLANATION_WORDS,
        max_chars=_MAX_EXPLANATION_CHARS,
    )
    if not text:
        return None
    return {"type": explanation_type, "text": text}


def _normalize_reason(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = _clamp_text(
        str(item.get("text") or ""),
        max_words=_MAX_REASON_WORDS,
        max_chars=_MAX_REASON_CHARS,
    )
    if not text:
        return None
    explanations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in item.get("explanations") or []:
        normalized = _normalize_explanation(raw)
        if normalized is None:
            continue
        key = (normalized["type"], _text_key(normalized["text"]))
        if key in seen:
            continue
        seen.add(key)
        explanations.append(normalized)
    return {"text": text, "explanations": explanations}


def _normalize_claim(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = _clamp_text(str(item.get("text") or ""))
    if not text:
        return None
    reasons: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in item.get("reasons") or []:
        normalized = _normalize_reason(raw)
        if normalized is None:
            continue
        key = _text_key(normalized["text"])
        if key in seen:
            continue
        seen.add(key)
        reasons.append(normalized)
    return {"text": text, "reasons": reasons}


def _flat_speaker_to_claims(item: dict[str, Any]) -> list[dict[str, Any]]:
    claim_text = _clamp_text(str(item.get("claim") or ""))
    if not claim_text:
        return []
    reasons: list[dict[str, Any]] = []
    seen_reasons: set[str] = set()
    for raw in item.get("evidence") or []:
        if not isinstance(raw, dict):
            continue
        evidence_text = _clamp_text(
            str(raw.get("text") or ""),
            max_words=_MAX_EXPLANATION_WORDS,
            max_chars=_MAX_EXPLANATION_CHARS,
        )
        if not evidence_text:
            continue
        explanation_type = str(raw.get("type") or "fact").strip().lower()
        if explanation_type not in _VALID_EXPLANATION_TYPES:
            explanation_type = "fact"
        reason_key = _text_key(evidence_text)
        if reason_key in seen_reasons:
            continue
        seen_reasons.add(reason_key)
        reasons.append(
            {
                "text": evidence_text,
                "explanations": [{"type": explanation_type, "text": evidence_text}],
            },
        )
    return [{"text": claim_text, "reasons": reasons}]


def _normalize_speaker(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    speaker_id = str(item.get("speaker_id") or "").strip()
    if not speaker_id:
        return None
    speaker_name = _clamp_text(str(item.get("speaker_name") or "")) or speaker_id
    speaker_type = str(item.get("speaker_type") or "").strip().lower()
    if speaker_type not in {"user", "agent"}:
        speaker_type = "user" if speaker_id == "user" else "agent"

    claims_raw = item.get("claims")
    claims: list[dict[str, Any]] = []
    if isinstance(claims_raw, list) and claims_raw:
        for raw_claim in claims_raw:
            normalized = _normalize_claim(raw_claim)
            if normalized is not None:
                claims.append(normalized)
    elif item.get("claim"):
        claims = _flat_speaker_to_claims(item)

    if not claims:
        return None

    return {
        "speaker_id": speaker_id,
        "speaker_name": speaker_name,
        "speaker_type": speaker_type,
        "claims": claims,
    }


def _explanation_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("type") or "fact").casefold(),
        _text_key(str(item.get("text") or "")),
    )


def _merge_explanations(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in existing + new:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_explanation(item)
        if normalized is None:
            continue
        key = _explanation_key(normalized)
        current = merged.get(key)
        if current is None or len(normalized["text"]) > len(current["text"]):
            merged[key] = normalized
    return list(merged.values())


def _merge_reasons(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in existing + new:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_reason(item)
        if normalized is None:
            continue
        key = _text_key(normalized["text"])
        current = merged.get(key)
        if current is None:
            merged[key] = normalized
            continue
        if len(normalized["text"]) > len(str(current.get("text") or "")):
            current["text"] = normalized["text"]
        current["explanations"] = _merge_explanations(
            current.get("explanations") or [],
            normalized.get("explanations") or [],
        )
    return list(merged.values())


def _merge_claims(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in existing + new:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_claim(item)
        if normalized is None:
            continue
        key = _text_key(normalized["text"])
        current = merged.get(key)
        if current is None:
            merged[key] = normalized
            continue
        if len(normalized["text"]) > len(str(current.get("text") or "")):
            current["text"] = normalized["text"]
        current["reasons"] = _merge_reasons(
            current.get("reasons") or [],
            normalized.get("reasons") or [],
        )
    return list(merged.values())


def _speaker_sort_key(speaker: dict[str, Any]) -> tuple[int, str]:
    speaker_id = str(speaker.get("speaker_id") or "")
    if speaker_id == "user":
        return (0, speaker_id)
    return (1, speaker_id)


def merge_speaker_summaries(
    previous: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in previous + new:
        normalized = _normalize_speaker(item)
        if normalized is None:
            continue
        speaker_id = normalized["speaker_id"]
        existing = merged.get(speaker_id)
        if existing is None:
            merged[speaker_id] = normalized
            continue
        if normalized.get("speaker_name"):
            existing["speaker_name"] = normalized["speaker_name"]
        existing["claims"] = _merge_claims(
            existing.get("claims") or [],
            normalized.get("claims") or [],
        )
    speakers = sorted(merged.values(), key=_speaker_sort_key)
    return speakers[:_MAX_SPEAKERS]


def _migrate_legacy_topic_claim(claim: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    claim_text = _clamp_text(str(claim.get("text") or ""))
    if not claim_text:
        return None
    reasons: list[dict[str, Any]] = []
    for package in claim.get("arguments") or []:
        if not isinstance(package, dict):
            continue
        reason = package.get("reason") if isinstance(package.get("reason"), dict) else {}
        reason_text = _clamp_text(
            str(reason.get("text") or ""),
            max_words=_MAX_REASON_WORDS,
            max_chars=_MAX_REASON_CHARS,
        )
        if not reason_text:
            continue
        explanations: list[dict[str, str]] = []
        for explanation in package.get("explanations") or []:
            if not isinstance(explanation, dict):
                continue
            normalized = _normalize_explanation(explanation)
            if normalized is not None:
                explanations.append(normalized)
        reasons.append({"text": reason_text, "explanations": explanations})
    return {
        "speaker_id": f"legacy_claim_{index}",
        "speaker_name": f"Topic position {index + 1}",
        "speaker_type": "agent",
        "claims": [{"text": claim_text, "reasons": reasons}],
    }


def _speakers_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    speakers_raw = summary.get("speakers")
    if isinstance(speakers_raw, list) and speakers_raw:
        result: list[dict[str, Any]] = []
        for item in speakers_raw:
            normalized = _normalize_speaker(item)
            if normalized is not None:
                result.append(normalized)
        return result

    claims_raw = summary.get("claims")
    if isinstance(claims_raw, list):
        migrated: list[dict[str, Any]] = []
        for index, claim in enumerate(claims_raw):
            if not isinstance(claim, dict):
                continue
            speaker = _migrate_legacy_topic_claim(claim, index=index)
            if speaker is not None:
                migrated.append(speaker)
        return migrated

    return []


def parse_argument_summary_response(raw: str) -> dict[str, Any]:
    parsed = _extract_json_object(raw)
    speakers: list[dict[str, Any]] = []
    speakers_raw = parsed.get("speakers")
    if isinstance(speakers_raw, list):
        for item in speakers_raw:
            normalized = _normalize_speaker(item)
            if normalized is not None:
                speakers.append(normalized)
    return {"speakers": speakers[:_MAX_SPEAKERS]}


def format_argument_summary_bullets(summary: dict[str, Any]) -> str:
    if summary.get("status") not in {_STATUS_READY, _STATUS_PENDING}:
        return ""

    lines: list[str] = []
    for speaker in _speakers_from_summary(summary):
        name = str(speaker.get("speaker_name") or speaker.get("speaker_id") or "Speaker").strip()
        claims = speaker.get("claims") or []
        if not claims:
            continue
        lines.append(f"- {name}")
        for claim in claims:
            claim_text = str(claim.get("text") or "").strip()
            if not claim_text:
                continue
            lines.append(f"  - Claim: {claim_text}")
            for reason in claim.get("reasons") or []:
                if not isinstance(reason, dict):
                    continue
                reason_text = str(reason.get("text") or "").strip()
                if not reason_text:
                    continue
                lines.append(f"    - Reason: {reason_text}")
                for explanation in reason.get("explanations") or []:
                    if not isinstance(explanation, dict):
                        continue
                    explanation_text = str(explanation.get("text") or "").strip()
                    if not explanation_text:
                        continue
                    explanation_type = str(explanation.get("type") or "fact")
                    type_label = _EXPLANATION_LABELS.get(explanation_type, "Fact")
                    lines.append(f"      - {type_label}: {explanation_text}")

    return "\n".join(lines)


_ARGUMENT_SUMMARY_PENDING_AGENT_GUIDANCE = (
    "Argument summary is still being updated in the background. "
    "Review the discussion history and do not repeat stances or evidence already stated."
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
    bullets = format_argument_summary_bullets(stored)
    if status == _STATUS_READY:
        return bullets or _ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE
    if status == _STATUS_PENDING:
        if bullets:
            return (
                f"{bullets}\n\n"
                "(Summary is still being refreshed; treat the bullets above as already covered.)"
            )
        return _ARGUMENT_SUMMARY_PENDING_AGENT_GUIDANCE
    return _ARGUMENT_SUMMARY_EMPTY_AGENT_GUIDANCE


def _previous_summary_json(session: ConversationSession) -> str:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if not stored:
        return "(none)"
    speakers = _speakers_from_summary(stored)
    if not speakers:
        return "(none)"
    return json.dumps({"speakers": speakers}, ensure_ascii=False, indent=2)


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
    result = invoke_chat_llm(llm, [SystemMessage(content=prompt)], user=session.user)
    raw = result.content if hasattr(result, "content") else str(result)
    return parse_argument_summary_response(raw)


def _summary_payload(*, status: str, data: dict[str, Any] | None = None, turn_count: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    if turn_count is not None:
        payload["turn_count"] = int(turn_count)
    if data:
        payload.update(data)
    return payload


def generate_argument_summary_for_session(session: ConversationSession) -> dict[str, Any]:
    if not session.turns.exists():
        return _summary_payload(status=_STATUS_EMPTY, data={"speakers": []})

    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    previous_speakers = _speakers_from_summary(stored) if stored else []

    try:
        parsed = extract_argument_summary(session=session)
    except Exception:
        logger.exception("argument_summary_generation_failed", extra={"session_id": session.id})
        if previous_speakers:
            payload = _summary_payload(
                status=_STATUS_READY,
                data={"speakers": previous_speakers},
                turn_count=session.turn_count,
            )
        else:
            payload = _summary_payload(
                status=_STATUS_EMPTY,
                data={"speakers": []},
                turn_count=session.turn_count,
            )
        session.argument_summary = payload
        session.save(update_fields=["argument_summary", "updated_at"])
        return session.argument_summary

    parsed_speakers = parsed.get("speakers") or []
    if parsed_speakers:
        merged = parsed_speakers
    else:
        merged = previous_speakers
    if not merged:
        payload = _summary_payload(
            status=_STATUS_EMPTY,
            data={"speakers": []},
            turn_count=session.turn_count,
        )
    else:
        payload = _summary_payload(
            status=_STATUS_READY,
            data={"speakers": merged},
            turn_count=session.turn_count,
        )

    session.argument_summary = payload
    session.save(update_fields=["argument_summary", "updated_at"])
    return payload


def ensure_argument_summary_for_closing_turn(session: ConversationSession) -> dict[str, Any]:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if stored and stored.get("status") == _STATUS_READY and _speakers_from_summary(stored):
        return stored
    return generate_argument_summary_for_session(session)


def mark_argument_summary_pending(session: ConversationSession) -> None:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    previous_speakers = _speakers_from_summary(stored) if stored else []
    data: dict[str, Any] = {"speakers": previous_speakers} if previous_speakers else {}
    session.argument_summary = _summary_payload(
        status=_STATUS_PENDING,
        data=data,
        turn_count=session.turn_count,
    )
    session.save(update_fields=["argument_summary", "updated_at"])


def get_argument_summary_for_session(session: ConversationSession) -> dict[str, Any]:
    stored = session.argument_summary if isinstance(session.argument_summary, dict) else None
    if stored and stored.get("status") in {_STATUS_READY, _STATUS_FAILED, _STATUS_EMPTY, _STATUS_PENDING}:
        return stored
    if not session.turns.exists():
        return _summary_payload(status=_STATUS_EMPTY, data={"speakers": []})
    return generate_argument_summary_for_session(session)


def _submit_background(func: Any, **kwargs: Any) -> None:
    _EXECUTOR.submit(func, **kwargs)


def _run_argument_summary_loop(*, session_id: int) -> None:
    try:
        initial_session = (
            ConversationSession.objects.filter(id=session_id)
            .select_related("user")
            .first()
        )
        tracing_user = initial_session.user if initial_session is not None else None
        with conversation_tracing_context(tracing_user):
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
        session.argument_summary = _summary_payload(
            status=_STATUS_EMPTY,
            data={"speakers": []},
            turn_count=session.turn_count,
        )
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


def finalize_argument_summary_on_conclusion(session: ConversationSession) -> None:
    from backend.conversation.services.session_serialization import is_session_concluded

    if not is_session_concluded(session):
        return
    schedule_argument_summary_for_session(session)

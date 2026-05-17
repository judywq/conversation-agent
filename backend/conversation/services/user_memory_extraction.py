from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.db import transaction
from langchain_core.messages import SystemMessage

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import UserMemory
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages

logger = logging.getLogger(__name__)

ALLOWED_MEMORY_TYPES = frozenset(
    {
        "profile",
        "learning_preference",
        "learning_goal",
        "weakness",
        "instruction",
    },
)
ALLOWED_ACTIONS = frozenset({"create", "skip"})
MIN_CONFIDENCE = 0.5
MAX_CONTENT_LENGTH = 2000

SENSITIVE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"(api[_ -]?key|token|secret|password|密码|密钥)", re.IGNORECASE),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"(身份证|护照|银行卡|精确地址|家庭住址)"),
]

_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="user-memory-extraction",
)


@dataclass(frozen=True)
class MemoryCandidate:
    action: str
    memory_type: str
    content: str
    confidence: float
    source_label: str = "conversation"
    reason: str = ""


@dataclass(frozen=True)
class CandidateValidationResult:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class PersistenceResult:
    created_count: int = 0
    skipped_count: int = 0
    created_ids: tuple[int, ...] = field(default_factory=tuple)


def normalize_memory_content(content: str) -> str:
    return " ".join((content or "").strip().casefold().split())


def _looks_sensitive(content: str) -> bool:
    return any(pattern.search(content) for pattern in SENSITIVE_PATTERNS)


def _looks_like_temporary_topic(content: str) -> bool:
    lowered = content.casefold()
    english_markers = (
        "current topic",
        "this session topic",
        "session topic",
    )
    return (
        "topic" in lowered
        or any(marker in lowered for marker in english_markers)
        or "当前话题" in content
        or "本轮话题" in content
    )


def _looks_like_cefr_sample(content: str) -> bool:
    lowered = content.casefold()
    return (
        "cefr sample" in lowered
        or bool(re.search(r"\b[a-c][12]\s+sample\b", lowered))
        or "cefr generated sample" in lowered
    )


def _weakness_has_enough_evidence(candidate: MemoryCandidate) -> bool:
    text = f"{candidate.content} {candidate.reason}".casefold()
    english_markers = (
        "explicit",
        "clearly stated",
        "long-term",
        "long term",
        "repeated",
        "recurring",
        "multiple times",
        "often struggles",
    )
    chinese_markers = ("明确", "长期", "反复", "多次")
    return any(marker in text for marker in english_markers) or any(
        marker in f"{candidate.content} {candidate.reason}" for marker in chinese_markers
    )


def _candidate_rejection_reason(
    candidate: MemoryCandidate,
    *,
    action: str,
    memory_type: str,
    content: str,
) -> str:
    reason = ""
    if action == "skip":
        reason = "skip"
    elif action not in ALLOWED_ACTIONS:
        reason = "invalid_action"
    elif memory_type not in ALLOWED_MEMORY_TYPES:
        reason = "invalid_memory_type"
    elif not content or len(content) > MAX_CONTENT_LENGTH:
        reason = "invalid_content"
    elif candidate.confidence < MIN_CONFIDENCE or candidate.confidence > 1.0:
        reason = "low_confidence"
    elif _looks_sensitive(content):
        reason = "sensitive"
    elif _looks_like_cefr_sample(content):
        reason = "cefr_sample"
    elif _looks_like_temporary_topic(content):
        reason = "temporary"
    elif memory_type == "weakness" and not _weakness_has_enough_evidence(candidate):
        reason = "weakness_insufficient_evidence"
    return reason


def validate_candidate(candidate: MemoryCandidate) -> CandidateValidationResult:
    action = (candidate.action or "").strip().lower()
    memory_type = (candidate.memory_type or "").strip().lower()
    content = (candidate.content or "").strip()
    reason = _candidate_rejection_reason(
        candidate,
        action=action,
        memory_type=memory_type,
        content=content,
    )
    if reason:
        return CandidateValidationResult(accepted=False, reason=reason)
    return CandidateValidationResult(accepted=True, reason="accepted")


def parse_memory_response(raw: str) -> list[MemoryCandidate]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    memories = parsed.get("memories") if isinstance(parsed, dict) else None
    if not isinstance(memories, list):
        return []

    candidates: list[MemoryCandidate] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        try:
            candidates.append(
                MemoryCandidate(
                    action=str(item.get("action") or "skip"),
                    memory_type=str(item.get("memory_type") or ""),
                    content=str(item.get("content") or ""),
                    confidence=float(item.get("confidence") or 0.0),
                    source_label=str(item.get("source_label") or "conversation"),
                    reason=str(item.get("reason") or ""),
                ),
            )
        except (TypeError, ValueError):
            continue
    return candidates


def build_memory_extraction_prompt(
    *,
    session: ConversationSession,
    turn: TurnRecord,
) -> str:
    recent_messages = turns_to_messages(get_short_term_turns(session, limit=6))
    return (
        "Extract only stable long-term user memories from the latest user utterance. "
        "Return strict JSON only with this shape: "
        '{"memories":[{"action":"create|skip",'
        '"memory_type":"profile|learning_preference|learning_goal|weakness|instruction",'
        '"content":"...","confidence":0.0,"reason":"..."}]}. '
        "The LLM only proposes candidates; backend validation decides persistence. "
        "Do not save temporary topics, generated CEFR sample text, "
        "sensitive information, or agent-only claims. "
        "For weakness, only save explicit long-term weakness or repeated evidence. "
        "Write every content and reason field in English, even if the user spoke another language. "
        f"Session topic: {session.topic}\n"
        f"Recent messages: {json.dumps(recent_messages, ensure_ascii=False)}\n"
        f"Latest user utterance: {turn.utterance}"
    )


def extract_memory_candidates(
    *,
    user: Any,
    session: ConversationSession,
    turn: TurnRecord,
    llm: Any | None = None,
) -> list[MemoryCandidate]:
    if turn.speaker_type != TurnRecord.SPEAKER_TYPE_USER:
        return []
    llm = llm or get_default_chat_llm()
    prompt = build_memory_extraction_prompt(session=session, turn=turn)
    result = llm.invoke([SystemMessage(content=prompt)])
    raw = result.content if hasattr(result, "content") else str(result)
    return parse_memory_response(raw)


def _duplicate_exists(*, user: Any, memory_type: str, content: str) -> bool:
    normalized = normalize_memory_content(content)
    memories = UserMemory.objects.filter(
        user=user,
        is_active=True,
        memory_type=memory_type,
    ).only("content")
    for memory in memories:
        if normalize_memory_content(memory.content) == normalized:
            return True
    return False


def persist_memory_candidates(
    *,
    user: Any,
    session: ConversationSession,
    turn: TurnRecord,
    candidates: list[MemoryCandidate],
) -> PersistenceResult:
    created_ids: list[int] = []
    skipped_count = 0
    with transaction.atomic():
        for candidate in candidates:
            validation = validate_candidate(candidate)
            if not validation.accepted:
                skipped_count += 1
                logger.info(
                    "memory_extraction_candidate_skipped",
                    extra={"reason": validation.reason},
                )
                continue

            memory_type = candidate.memory_type.strip().lower()
            content = candidate.content.strip()
            if _duplicate_exists(user=user, memory_type=memory_type, content=content):
                skipped_count += 1
                logger.info(
                    "memory_extraction_candidate_skipped",
                    extra={"reason": "duplicate"},
                )
                continue

            memory = UserMemory.objects.create(
                user=user,
                memory_type=memory_type,
                content=content,
                source_label="conversation_extraction",
                source_uri=f"conversation:{session.id}:turn:{turn.id}",
                confidence=candidate.confidence,
                metadata={
                    "kind": "conversation_extraction",
                    "session_id": session.id,
                    "turn_id": turn.id,
                    "reason": candidate.reason,
                },
            )
            created_ids.append(memory.id)
            logger.info(
                "memory_extraction_candidate_created",
                extra={
                    "memory_id": memory.id,
                    "session_id": session.id,
                    "turn_id": turn.id,
                    "memory_type": memory_type,
                },
            )

    return PersistenceResult(
        created_count=len(created_ids),
        skipped_count=skipped_count,
        created_ids=tuple(created_ids),
    )


def _submit_background(func: Any, **kwargs: Any) -> None:
    _EXECUTOR.submit(func, **kwargs)


def run_memory_extraction_for_turn(
    *,
    user_id: int,
    session_id: int,
    turn_id: int,
) -> None:
    user_model = get_user_model()
    user = user_model.objects.filter(id=user_id).first()
    session = ConversationSession.objects.filter(id=session_id, user_id=user_id).first()
    turn = TurnRecord.objects.filter(id=turn_id, session_id=session_id).first()
    if user is None or session is None or turn is None:
        logger.info(
            "memory_extraction_missing_records",
            extra={"user_id": user_id, "session_id": session_id, "turn_id": turn_id},
        )
        close_old_connections()
        return

    try:
        candidates = extract_memory_candidates(user=user, session=session, turn=turn)
        persist_memory_candidates(
            user=user,
            session=session,
            turn=turn,
            candidates=candidates,
        )
    except Exception:
        logger.exception(
            "memory_extraction_failed",
            extra={"user_id": user_id, "session_id": session_id, "turn_id": turn_id},
        )
    finally:
        close_old_connections()


def schedule_memory_extraction_for_turn(turn: TurnRecord) -> None:
    if not getattr(settings, "USER_MEMORY_EXTRACTION_ENABLED", True):
        return
    if turn.speaker_type != TurnRecord.SPEAKER_TYPE_USER:
        return

    user_id = turn.session.user_id
    session_id = turn.session_id
    turn_id = turn.id

    transaction.on_commit(
        lambda: _submit_background(
            run_memory_extraction_for_turn,
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
        ),
    )

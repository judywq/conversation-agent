from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from django.conf import settings

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", flags=re.IGNORECASE)


@dataclass(frozen=True)
class DuplicateScore:
    sequence_ratio: float
    token_jaccard: float
    score: float
    candidate_useful_token_count: int


@dataclass(frozen=True)
class DuplicateDetectionResult:
    is_duplicate: bool
    score: float
    threshold: float
    matched_utterance: str
    matched_speaker: str
    matched_turn_id: int | None
    turn_index: int | None
    subturn_index: int | None
    reason: str = ""

    def to_log_context(self) -> dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "score": self.score,
            "threshold": self.threshold,
            "matched_utterance": self.matched_utterance,
            "matched_speaker": self.matched_speaker,
            "matched_turn_id": self.matched_turn_id,
            "turn_index": self.turn_index,
            "subturn_index": self.subturn_index,
            "reason": self.reason,
        }


def normalize_utterance(text: str) -> str:
    normalized = str(text or "").casefold()
    normalized = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", normalized)
    normalized = normalized.replace("_", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(text: str) -> tuple[str, ...]:
    normalized = normalize_utterance(text)
    return tuple(match.group(0) for match in _TOKEN_RE.finditer(normalized))


def _token_jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def compute_duplicate_score(candidate: str, prior: str) -> DuplicateScore:
    candidate_normalized = normalize_utterance(candidate)
    prior_normalized = normalize_utterance(prior)
    if not candidate_normalized or not prior_normalized:
        return DuplicateScore(
            sequence_ratio=0.0,
            token_jaccard=0.0,
            score=0.0,
            candidate_useful_token_count=0,
        )

    candidate_tokens = _tokens(candidate)
    prior_tokens = _tokens(prior)
    sequence_ratio = SequenceMatcher(
        None,
        candidate_normalized,
        prior_normalized,
    ).ratio()
    token_jaccard = _token_jaccard(candidate_tokens, prior_tokens)
    score = (0.6 * sequence_ratio) + (0.4 * token_jaccard)
    return DuplicateScore(
        sequence_ratio=sequence_ratio,
        token_jaccard=token_jaccard,
        score=score,
        candidate_useful_token_count=len(candidate_tokens),
    )


def _setting_float(name: str, default: float) -> float:
    value = getattr(settings, name, default)
    if value in (None, ""):
        return default
    return float(value)


def _setting_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    if value in (None, ""):
        return default
    return int(value)


def empty_duplicate_result(
    *,
    threshold: float,
    reason: str = "",
) -> DuplicateDetectionResult:
    return DuplicateDetectionResult(
        is_duplicate=False,
        score=0.0,
        threshold=threshold,
        matched_utterance="",
        matched_speaker="",
        matched_turn_id=None,
        turn_index=None,
        subturn_index=None,
        reason=reason,
    )


def apply_duplicate_detection_to_turn(
    turn: TurnRecord,
    result: DuplicateDetectionResult,
) -> TurnRecord:
    """Persist duplicate detection metadata on an agent turn for admin inspection."""
    if turn.speaker_type != TurnRecord.SPEAKER_TYPE_AGENT:
        return turn

    turn.duplicate_similarity_score = result.score
    turn.duplicate_is_repetition = result.is_duplicate
    turn.duplicate_threshold = result.threshold
    turn.duplicate_matched_utterance = result.matched_utterance or ""
    turn.duplicate_matched_speaker = result.matched_speaker or ""
    turn.duplicate_matched_turn_index = result.turn_index
    turn.duplicate_matched_subturn_index = result.subturn_index
    turn.duplicate_reason = result.reason or ""
    turn.duplicate_matched_turn_id = result.matched_turn_id
    turn.save(
        update_fields=[
            "duplicate_similarity_score",
            "duplicate_is_repetition",
            "duplicate_threshold",
            "duplicate_matched_utterance",
            "duplicate_matched_speaker",
            "duplicate_matched_turn_index",
            "duplicate_matched_subturn_index",
            "duplicate_reason",
            "duplicate_matched_turn",
            "updated_at",
        ],
    )
    return turn


def detect_duplicate_agent_utterance(
    session: ConversationSession,
    candidate_utterance: str,
    *,
    threshold: float | None = None,
    min_useful_tokens: int | None = None,
    recent_limit: int | None = None,
) -> DuplicateDetectionResult:
    resolved_threshold = (
        threshold
        if threshold is not None
        else _setting_float("AGENT_UTTERANCE_DUPLICATE_THRESHOLD", 0.75)
    )
    resolved_min_tokens = (
        min_useful_tokens
        if min_useful_tokens is not None
        else _setting_int("AGENT_UTTERANCE_DUPLICATE_MIN_TOKENS", 4)
    )
    resolved_recent_limit = (
        recent_limit
        if recent_limit is not None
        else _setting_int("AGENT_UTTERANCE_DUPLICATE_RECENT_LIMIT", 20)
    )

    candidate_tokens = _tokens(candidate_utterance)
    if len(candidate_tokens) < resolved_min_tokens:
        return empty_duplicate_result(
            threshold=resolved_threshold,
            reason="candidate_below_min_useful_tokens",
        )

    prior_turns = (
        TurnRecord.objects.filter(
            session=session,
            speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        )
        .order_by("-turn_index", "-subturn_index", "-id")[:resolved_recent_limit]
    )

    best_turn: TurnRecord | None = None
    best_score = 0.0
    for turn in prior_turns:
        scored = compute_duplicate_score(candidate_utterance, turn.utterance)
        if scored.score > best_score:
            best_score = scored.score
            best_turn = turn

    if best_turn is None:
        return empty_duplicate_result(
            threshold=resolved_threshold,
            reason="no_prior_agent_turns",
        )

    is_duplicate = best_score >= resolved_threshold
    return DuplicateDetectionResult(
        is_duplicate=is_duplicate,
        score=best_score,
        threshold=resolved_threshold,
        matched_utterance=best_turn.utterance,
        matched_speaker=best_turn.speaker,
        matched_turn_id=best_turn.id,
        turn_index=best_turn.turn_index,
        subturn_index=best_turn.subturn_index,
        reason="duplicate_threshold_met" if is_duplicate else "below_threshold",
    )

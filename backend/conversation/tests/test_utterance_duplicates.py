from __future__ import annotations

import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.utterance_duplicates import compute_duplicate_score
from backend.conversation.services.utterance_duplicates import (
    detect_duplicate_agent_utterance,
)
from backend.conversation.services.utterance_duplicates import normalize_utterance

DEFAULT_THRESHOLD = 0.75
DUPLICATE_UTTERANCE = (
    "Daily speaking practice improves fluency because it builds automatic recall."
)
MIN_USEFUL_TOKENS = 4


def test_normalize_utterance_case_punctuation_and_spacing() -> None:
    assert (
        normalize_utterance("  Well, I THINK this works!  ")
        == "well i think this works"
    )


def test_compute_duplicate_score_uses_weighted_sequence_and_token_overlap() -> None:
    result = compute_duplicate_score(
        "I think daily speaking practice is useful for fluency.",
        "I think daily speaking practice is useful for fluency.",
    )

    assert result.sequence_ratio == pytest.approx(1.0)
    assert result.token_jaccard == pytest.approx(1.0)
    assert result.score == pytest.approx(1.0)
    assert result.candidate_useful_token_count >= MIN_USEFUL_TOKENS


def test_compute_duplicate_score_does_not_over_trigger_partial_overlap() -> None:
    result = compute_duplicate_score(
        "I think daily speaking practice is useful for fluency.",
        "We should compare tuition costs and campus housing.",
    )

    assert result.score < DEFAULT_THRESHOLD


@pytest.mark.django_db
def test_detect_duplicate_agent_utterance_returns_best_same_session_agent_match(
    user,
) -> None:
    session = ConversationSession.objects.create(user=user, topic="practice")
    other_session = ConversationSession.objects.create(user=user, topic="other")
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Daily speaking practice improves fluency.",
        turn_index=0,
        subturn_index=0,
    )
    prior = TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=DUPLICATE_UTTERANCE,
        turn_index=1,
        subturn_index=0,
    )
    TurnRecord.objects.create(
        session=other_session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=DUPLICATE_UTTERANCE,
        turn_index=0,
        subturn_index=0,
    )

    result = detect_duplicate_agent_utterance(
        session,
        DUPLICATE_UTTERANCE,
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=20,
    )

    assert result.is_duplicate is True
    assert result.matched_turn_id == prior.id
    assert result.matched_speaker == "agent_1"
    assert result.matched_utterance == prior.utterance
    assert result.turn_index == 1
    assert result.subturn_index == 0
    assert result.score >= result.threshold


@pytest.mark.django_db
def test_detect_duplicate_agent_utterance_ignores_short_candidate(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="practice")
    TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="I agree.",
        turn_index=0,
        subturn_index=0,
    )

    result = detect_duplicate_agent_utterance(
        session,
        "I agree.",
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=20,
    )

    assert result.is_duplicate is False
    assert result.matched_turn_id is None
    assert result.reason == "candidate_below_min_useful_tokens"


@pytest.mark.django_db
def test_detect_duplicate_agent_utterance_uses_settings_defaults(
    user,
    settings,
) -> None:
    settings.AGENT_UTTERANCE_DUPLICATE_THRESHOLD = DEFAULT_THRESHOLD
    settings.AGENT_UTTERANCE_DUPLICATE_MIN_TOKENS = MIN_USEFUL_TOKENS
    settings.AGENT_UTTERANCE_DUPLICATE_RECENT_LIMIT = 20
    session = ConversationSession.objects.create(user=user, topic="practice")
    prior = TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=DUPLICATE_UTTERANCE,
        turn_index=0,
        subturn_index=0,
    )

    result = detect_duplicate_agent_utterance(
        session,
        DUPLICATE_UTTERANCE,
    )

    assert result.is_duplicate is True
    assert result.threshold == DEFAULT_THRESHOLD
    assert result.matched_turn_id == prior.id


@pytest.mark.django_db
def test_detect_duplicate_agent_utterance_does_not_match_user_turns(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="practice")
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance=DUPLICATE_UTTERANCE,
        turn_index=0,
        subturn_index=0,
    )

    result = detect_duplicate_agent_utterance(
        session,
        DUPLICATE_UTTERANCE,
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=20,
    )

    assert result.is_duplicate is False
    assert result.matched_turn_id is None


@pytest.mark.django_db
def test_detect_duplicate_agent_utterance_respects_recent_limit(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="practice")
    older = TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=DUPLICATE_UTTERANCE,
        turn_index=0,
        subturn_index=0,
    )
    TurnRecord.objects.create(
        session=session,
        speaker="agent_2",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="We should compare tuition costs and campus housing.",
        turn_index=1,
        subturn_index=0,
    )

    result = detect_duplicate_agent_utterance(
        session,
        older.utterance,
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=1,
    )

    assert result.is_duplicate is False

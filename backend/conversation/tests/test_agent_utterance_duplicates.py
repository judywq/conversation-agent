from __future__ import annotations

import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnEngineLog
from backend.conversation.models import TurnRecord
from backend.conversation.services.turn_processor import append_turn

DEFAULT_THRESHOLD = 0.75
DUPLICATE_UTTERANCE = (
    "Daily speaking practice improves fluency because it builds automatic recall."
)
MIN_USEFUL_TOKENS = 4


@pytest.mark.django_db
def test_duplicate_detection_result_can_be_logged_without_changing_turn(user) -> None:
    from backend.conversation import consumers

    session = ConversationSession.objects.create(user=user, topic="practice")
    agent = AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        personality={"persona_name": "Fact Checker"},
    )
    prior = append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance=DUPLICATE_UTTERANCE,
        source="llm",
    ).turn

    duplicate_result = consumers.detect_duplicate_agent_utterance(
        session,
        DUPLICATE_UTTERANCE,
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=20,
    )

    assert duplicate_result.is_duplicate is True

    consumers.log_agent_utterance_duplicate_detection(
        session=session,
        agent_id=agent.agent_id,
        result=duplicate_result,
        correlation_id="test-correlation",
        turn_index=session.turn_count,
    )

    log = TurnEngineLog.objects.get(event="agent_utterance_duplicate_detected")
    assert log.session == session
    assert log.context["speaker"] == "agent_1"
    assert log.context["is_duplicate"] is True
    assert log.context["matched_turn_id"] == prior.id
    assert log.context["matched_utterance"] == prior.utterance
    assert log.context["future_policy"] == "regeneration_or_replanning_not_implemented"


@pytest.mark.django_db
def test_non_duplicate_detection_result_does_not_create_duplicate_log(user) -> None:
    from backend.conversation import consumers

    session = ConversationSession.objects.create(user=user, topic="practice")
    AgentProfile.objects.create(
        session=session,
        agent_id="agent_1",
        personality={"persona_name": "Fact Checker"},
    )
    result = consumers.detect_duplicate_agent_utterance(
        session,
        "This is a new contribution about study planning.",
        threshold=DEFAULT_THRESHOLD,
        min_useful_tokens=MIN_USEFUL_TOKENS,
        recent_limit=20,
    )

    consumers.log_agent_utterance_duplicate_detection(
        session=session,
        agent_id="agent_1",
        result=result,
        correlation_id="test-correlation",
        turn_index=session.turn_count,
    )

    duplicate_logs = TurnEngineLog.objects.filter(
        event="agent_utterance_duplicate_detected",
    )
    assert duplicate_logs.count() == 0

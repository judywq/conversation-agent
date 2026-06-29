import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.conversation_phase import has_unanswered_user_question
from backend.conversation.services.conversation_phase import is_hard_cap_reached
from backend.conversation.services.conversation_phase import is_past_max_turns
from backend.conversation.services.conversation_phase import should_request_closing_agent
from backend.conversation.services.conversation_phase import should_terminate
from backend.conversation.services.conversation_phase import user_close_pending
from backend.conversation.services.conversation_phase import user_turns_allowed
from backend.conversation.services.turn_processor import TurnMetadata
from backend.conversation.services.turn_processor import append_turn


@pytest.mark.django_db
def test_user_turns_allowed_before_max(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=9)
    assert user_turns_allowed(session) is True
    assert is_past_max_turns(session) is False


@pytest.mark.django_db
def test_user_turns_blocked_at_max(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=10)
    assert user_turns_allowed(session) is False
    assert is_past_max_turns(session) is True


@pytest.mark.django_db
def test_has_unanswered_user_question_detects_interrogative(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=1)
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="What do you think about dorms?",
        source="text",
    )
    assert has_unanswered_user_question(session) is True


@pytest.mark.django_db
def test_should_request_closing_agent_after_max_without_open_question(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=10)
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"})
    assert should_request_closing_agent(session) is True


@pytest.mark.django_db
def test_should_not_request_closing_while_user_question_open(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=10)
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"})
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Why is campus housing so expensive?",
        source="text",
    )
    assert should_request_closing_agent(session) is False


@pytest.mark.django_db
def test_hard_cap_terminates(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=14)
    assert is_hard_cap_reached(session) is True
    assert should_terminate(session) is True


@pytest.mark.django_db
def test_past_max_does_not_immediately_terminate_without_close(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=10, turn_count=10)
    assert should_terminate(session) is False


@pytest.mark.django_db
def test_user_close_request_triggers_closing_before_max(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=25, turn_count=5)
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"})
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I want to finish the conversation.",
        metadata=TurnMetadata(
            type="DIRECTIVES",
            subtype="request_closing",
            target="everyone",
            content_requirement="requests to end the session",
            retrieval_requirement="",
        ),
        source="text",
    )

    assert user_close_pending(session) is True
    assert should_request_closing_agent(session) is True
    assert user_turns_allowed(session) is False
    assert should_terminate(session) is False


@pytest.mark.django_db
def test_user_close_request_terminates_after_agent_close(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=25, turn_count=5)
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "Discussion Driver"})
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Can we wrap up?",
        metadata=TurnMetadata(
            type="DIRECTIVES",
            subtype="request_closing",
            target="everyone",
            content_requirement="requests to end the session",
            retrieval_requirement="",
        ),
        source="text",
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Thanks everyone for a great chat.",
        metadata=TurnMetadata(
            type="DECLARATIONS",
            subtype="close_session",
            target="everyone",
            content_requirement="",
            retrieval_requirement="",
        ),
        source="text",
    )

    assert user_close_pending(session) is False
    assert should_terminate(session) is True

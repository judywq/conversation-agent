import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.makeshift import invite_user
from backend.conversation.services.turn_manager import decide_next_speaker
from backend.conversation.services.turn_processor import append_turn


@pytest.mark.django_db
def test_termination_when_max_turns_reached(user):
    session = ConversationSession.objects.create(user=user, topic="t", max_turns=2, turn_count=2)
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.terminate is True


@pytest.mark.django_db
def test_forced_user_turn_has_priority(user):
    session = ConversationSession.objects.create(
        user=user,
        topic="t",
        pending_forced_user_turn=True,
        turn_count=1,
    )
    decision = decide_next_speaker(session, user_volunteered=False, last_user_turn_index=None)
    assert decision.terminate is False
    assert decision.next_speaker == "user"


@pytest.mark.django_db
def test_makeshift_invite_sets_pending_forced_user_turn(user):
    session = ConversationSession.objects.create(user=user, topic="t", previous_speaker="agent_1")
    turn = invite_user(session)
    session.refresh_from_db()
    assert turn.speaker_type == TurnRecord.SPEAKER_TYPE_MAKESHIFT
    assert session.pending_forced_user_turn is True


@pytest.mark.django_db
def test_append_turn_updates_session_state(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    processed = append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="hello",
        source="text",
    )
    session.refresh_from_db()
    assert processed.turn.turn_index == 0
    assert session.turn_count == 1
    assert session.previous_speaker == "user"


@pytest.mark.django_db
def test_pause_flag_persists(user):
    session = ConversationSession.objects.create(user=user, topic="t", paused=True)
    session.refresh_from_db()
    assert session.paused is True


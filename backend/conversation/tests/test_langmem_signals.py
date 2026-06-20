import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.langmem_extraction import langmem_extraction_enabled


@pytest.mark.django_db
def test_langmem_signal_schedules_on_user_turn(user, monkeypatch):
    scheduled = []
    session = ConversationSession.objects.create(user=user, topic="class discussion")

    monkeypatch.setattr(
        "backend.conversation.services.langmem_extraction.schedule_langmem_extraction_for_turn",
        lambda turn: scheduled.append(turn.id),
    )

    turn = TurnRecord.objects.create(
        session=session,
        turn_index=1,
        subturn_index=0,
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        speaker=str(user.id),
        utterance="I love hiking on weekends.",
    )

    assert scheduled == [turn.id]


@pytest.mark.django_db
def test_langmem_signal_schedules_on_agent_turn(user, monkeypatch):
    scheduled = []
    session = ConversationSession.objects.create(user=user, topic="class discussion")

    monkeypatch.setattr(
        "backend.conversation.services.langmem_extraction.schedule_langmem_extraction_for_turn",
        lambda turn: scheduled.append(turn.id),
    )

    turn = TurnRecord.objects.create(
        session=session,
        turn_index=2,
        subturn_index=0,
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        speaker="fact_checker",
        utterance="That sounds like a great hobby.",
    )

    assert scheduled == [turn.id]


def test_langmem_extraction_respects_settings(settings):
    settings.SPEAKER_PROFILES_ENABLED = True
    settings.LANGMEM_ENABLED = True
    settings.LANGMEM_PROFILE_EXTRACTION_ENABLED = False
    assert langmem_extraction_enabled() is False

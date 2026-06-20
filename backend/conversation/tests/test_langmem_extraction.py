import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.langmem_extraction import turns_to_langmem_messages


@pytest.mark.django_db
def test_turns_to_langmem_messages_prefixes_speakers(user):
    session = ConversationSession.objects.create(user=user, topic="exercise habits")
    turns = [
        TurnRecord(
            session=session,
            turn_index=1,
            subturn_index=0,
            speaker_type=TurnRecord.SPEAKER_TYPE_USER,
            speaker=str(user.id),
            utterance="I go jogging twice a week.",
        ),
        TurnRecord(
            session=session,
            turn_index=2,
            subturn_index=0,
            speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
            speaker="fact_checker",
            utterance="That sounds like a healthy routine.",
        ),
        TurnRecord(
            session=session,
            turn_index=3,
            subturn_index=0,
            speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
            speaker="idea_explorer",
            utterance="I usually stretch before jogging too.",
        ),
    ]

    messages = turns_to_langmem_messages(turns)

    assert messages == [
        {"role": "user", "content": "[user] I go jogging twice a week."},
        {"role": "assistant", "content": "[fact_checker] That sounds like a healthy routine."},
        {"role": "assistant", "content": "[idea_explorer] I usually stretch before jogging too."},
    ]


@pytest.mark.django_db
def test_run_langmem_extraction_routes_by_turn_type(user, monkeypatch):
    from backend.conversation.services.langmem_extraction import run_langmem_extraction_for_turn

    calls: list[tuple[str, str | None]] = []
    session = ConversationSession.objects.create(user=user, topic="class discussion")

    def _capture_extract(profile_user, messages, *, agent_slug=None, store=None):
        calls.append((profile_user.id, agent_slug))

    monkeypatch.setattr(
        "backend.conversation.services.langmem_extraction.extract_and_update_profiles",
        _capture_extract,
    )

    user_turn = TurnRecord.objects.create(
        session=session,
        turn_index=1,
        subturn_index=0,
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        speaker=str(user.id),
        utterance="I love hiking on weekends.",
    )
    run_langmem_extraction_for_turn(
        user_id=user.id,
        session_id=session.id,
        turn_id=user_turn.id,
    )
    assert calls == [(user.id, None)]

    calls.clear()
    agent_turn = TurnRecord.objects.create(
        session=session,
        turn_index=2,
        subturn_index=0,
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        speaker="fact_checker",
        utterance="Hiking is great exercise.",
    )
    run_langmem_extraction_for_turn(
        user_id=user.id,
        session_id=session.id,
        turn_id=agent_turn.id,
    )
    assert calls == [(user.id, "fact_checker")]

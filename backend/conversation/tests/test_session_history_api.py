import json

import pytest
from django.urls import reverse

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.session_serialization import can_continue_session
from backend.conversation.services.session_serialization import is_session_concluded
from backend.conversation.services.session_serialization import session_detail_to_dict
from backend.conversation.services.session_serialization import session_summary_to_dict


@pytest.mark.django_db
def test_session_summary_to_dict_includes_metadata(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Campus housing",
        turn_count=3,
        max_turns=5,
        terminate=True,
        argument_summary={"status": "ready", "speakers": []},
    )

    payload = session_summary_to_dict(session)

    assert payload["id"] == session.id
    assert payload["topic"] == "Campus housing"
    assert payload["turn_count"] == 3
    assert payload["argument_summary_status"] == "ready"
    assert payload["session_concluded"] is True


@pytest.mark.django_db
def test_session_concluded_flags(user) -> None:
    stopped = ConversationSession.objects.create(
        user=user,
        topic="Stopped",
        turn_count=2,
        max_turns=25,
        terminate=True,
    )
    interrupted = ConversationSession.objects.create(
        user=user,
        topic="Interrupted",
        turn_count=2,
        max_turns=25,
        terminate=False,
    )
    empty = ConversationSession.objects.create(
        user=user,
        topic="Empty",
        turn_count=0,
        max_turns=25,
        terminate=False,
    )

    assert is_session_concluded(stopped) is True
    assert is_session_concluded(interrupted) is False
    assert is_session_concluded(empty) is False
    assert session_summary_to_dict(stopped)["session_concluded"] is True
    assert session_summary_to_dict(interrupted)["session_concluded"] is False
    assert session_detail_to_dict(stopped)["session_concluded"] is True


@pytest.mark.django_db
def test_can_continue_session_flags(user) -> None:
    # Past hard cap (max_turns + extension) — should_terminate without relying on closing turns
    ended = ConversationSession.objects.create(
        user=user,
        topic="Finished",
        turn_count=9,
        max_turns=5,
        terminate=False,
    )
    stopped = ConversationSession.objects.create(
        user=user,
        topic="Stopped",
        turn_count=2,
        max_turns=5,
        terminate=True,
    )
    interrupted = ConversationSession.objects.create(
        user=user,
        topic="Left early",
        turn_count=2,
        max_turns=5,
        terminate=False,
    )
    empty = ConversationSession.objects.create(
        user=user,
        topic="Never started",
        turn_count=0,
        max_turns=5,
        terminate=False,
    )

    assert can_continue_session(ended) is False
    assert can_continue_session(stopped) is False
    assert can_continue_session(interrupted) is True
    assert can_continue_session(empty) is True
    assert session_summary_to_dict(interrupted)["can_continue"] is True
    assert session_summary_to_dict(stopped)["can_continue"] is False
    assert session_summary_to_dict(empty)["can_continue"] is True
    assert session_summary_to_dict(ended)["can_continue"] is False


@pytest.mark.django_db
def test_session_detail_to_dict_includes_turns_and_summary(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="AI in schools",
        turn_count=1,
        argument_summary={
            "status": "ready",
            "claims": [
                {
                    "text": "AI helps learning",
                    "arguments": [
                        {
                            "type": "argument",
                            "reason": {"text": "Adaptive feedback"},
                            "explanations": [],
                        },
                    ],
                },
            ],
        },
    )
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="I think AI can personalize study plans.",
        turn_index=1,
    )

    payload = session_detail_to_dict(session)

    assert len(payload["turns"]) == 1
    assert payload["turns"][0]["utterance"].startswith("I think AI")
    assert payload["argument_summary"]["status"] == "ready"
    assert payload["argument_summary"]["claims"][0]["text"] == "AI helps learning"


@pytest.mark.django_db
def test_session_list_api_returns_only_user_sessions(user, client) -> None:
    from backend.users.tests.factories import UserFactory

    other = UserFactory()
    ConversationSession.objects.create(user=user, topic="Mine", turn_count=2)
    ConversationSession.objects.create(user=other, topic="Theirs", turn_count=2)
    ConversationSession.objects.create(user=user, topic="Empty", turn_count=0)

    client.force_login(user)
    response = client.get(reverse("conversation-session-list"))

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["topic"] == "Mine"


@pytest.mark.django_db
def test_session_detail_api_returns_turns_for_owner(user, client) -> None:
    session = ConversationSession.objects.create(user=user, topic="History test", turn_count=1)
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Hello everyone.",
        turn_index=1,
    )

    client.force_login(user)
    url = reverse("conversation-session-detail", kwargs={"session_id": session.id})
    response = client.get(url)

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "History test"
    assert len(body["turns"]) == 1
    assert body["turns"][0]["utterance"] == "Hello everyone."


@pytest.mark.django_db
def test_session_detail_api_rejects_other_users(client) -> None:
    from backend.users.tests.factories import UserFactory

    owner = UserFactory()
    other = UserFactory()
    session = ConversationSession.objects.create(user=owner, topic="Private", turn_count=1)
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Secret",
        turn_index=1,
    )

    client.force_login(other)
    url = reverse("conversation-session-detail", kwargs={"session_id": session.id})
    response = client.get(url)

    assert response.status_code == 404

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import UserAudio
from backend.conversation.services.session_serialization import session_detail_to_dict
from backend.conversation.services.session_serialization import turn_record_to_dict


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
@override_settings(DEBUG=True, DOMAIN_NAME="localhost:8000", MEDIA_URL="/media/")
def test_user_audio_upload_returns_absolute_url(api_client, user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Upload test")
    audio = SimpleUploadedFile("user_recording.webm", b"fake-webm", content_type="audio/webm")

    response = api_client.post(
        reverse("conversation-user-audio"),
        {"session_id": session.id, "audio": audio},
        format="multipart",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"]
    assert body["audio_url"].startswith("http://localhost:8000/media/")
    assert "conversation/user_audio/" in body["audio_url"]
    assert UserAudio.objects.filter(id=body["id"], session=session, user=user).exists()


@pytest.mark.django_db
@override_settings(DEBUG=True, DOMAIN_NAME="localhost:8000", MEDIA_URL="/media/")
def test_turn_serialization_absolutizes_relative_audio_url(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="Relative audio")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Hello",
        turn_index=1,
        audio_url="/media/conversation/user_audio/session_1/user_1/clip.webm",
        source="mic",
    )

    payload = turn_record_to_dict(turn=turn, session=session)

    assert (
        payload["audio_url"]
        == "http://localhost:8000/media/conversation/user_audio/session_1/user_1/clip.webm"
    )


@pytest.mark.django_db
@override_settings(DEBUG=True, DOMAIN_NAME="localhost:8000", MEDIA_URL="/media/")
def test_session_detail_absolutizes_relative_audio_url(user) -> None:
    session = ConversationSession.objects.create(user=user, topic="History audio", turn_count=1)
    TurnRecord.objects.create(
        session=session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="Mic turn",
        turn_index=1,
        audio_url="/media/conversation/user_audio/old.webm",
        source="mic",
    )
    TurnRecord.objects.create(
        session=session,
        speaker="agent_a",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Agent reply",
        turn_index=2,
        audio_url="http://localhost:8000/media/audio/agent.mp3",
    )

    payload = session_detail_to_dict(session)

    assert payload["turns"][0]["audio_url"] == "http://localhost:8000/media/conversation/user_audio/old.webm"
    assert payload["turns"][1]["audio_url"] == "http://localhost:8000/media/audio/agent.mp3"

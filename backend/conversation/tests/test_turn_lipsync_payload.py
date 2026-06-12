from asgiref.sync import async_to_sync
import pytest

from backend.conversation.consumers import ConversationConsumer
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord


@pytest.mark.django_db
def test_turn_to_dict_includes_lipsync_for_agent_turns(user):
    session = ConversationSession.objects.create(user=user, topic="Avatars")
    turn = TurnRecord.objects.create(
        session=session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="Hello there.",
        utterance_tts="Hello there.",
        turn_index=0,
        subturn_index=0,
        audio_url="http://example.test/media/audio/test.mp3",
        lipsync={
            "words": ["Hello", "there."],
            "wtimes": [0, 400],
            "wdurations": [400, 500],
        },
    )

    consumer = ConversationConsumer()
    payload = async_to_sync(consumer._turn_to_dict)(turn)

    assert payload["lipsync"]["words"] == ["Hello", "there."]
    assert payload["audio_url"] == "http://example.test/media/audio/test.mp3"

import inspect
from asgiref.sync import async_to_sync
import pytest

from backend.conversation.consumers import ConversationConsumer
from backend.conversation.models import ConversationSession


def test_resume_session_receive_json_uses_async_can_continue_wrapper() -> None:
    source = inspect.getsource(ConversationConsumer.receive_json)
    assert "await self._can_continue_session(session)" in source
    assert "if not can_continue_session(session)" not in source


@pytest.mark.django_db
def test_resume_session_receive_json_on_interrupted_session(user) -> None:
    session = ConversationSession.objects.create(
        user=user,
        topic="Interrupted discussion",
        turn_count=2,
        max_turns=25,
        terminate=False,
        pending_forced_user_turn=True,
    )

    consumer = ConversationConsumer()
    consumer.scope = {"user": user}
    consumer.session_id = None
    sent: list[dict] = []

    async def capture_send_json(payload: dict) -> None:
        sent.append(payload)

    consumer.send_json = capture_send_json

    async def mock_get_session(session_id: int) -> ConversationSession:
        assert session_id == session.id
        return session

    async def mock_can_continue(session: ConversationSession) -> bool:
        assert session.id == session.id
        return True

    async def mock_profile_gate() -> dict:
        return {"profile_completed": True, "cefr_level": "B1"}

    async def mock_turns_payload(session_id: int) -> list[dict]:
        return []

    async def mock_participants(session_id: int) -> list[dict]:
        return []

    consumer._get_session = mock_get_session
    consumer._can_continue_session = mock_can_continue
    consumer._get_profile_gate_state = mock_profile_gate
    consumer._session_turns_payload = mock_turns_payload
    consumer._participants_payload = mock_participants

    async_to_sync(consumer.receive_json)({"type": "resume_session", "session_id": session.id})

    message_types = [message["type"] for message in sent]
    assert "session_resumed" in message_types
    resumed = next(message for message in sent if message["type"] == "session_resumed")
    assert resumed["session_id"] == session.id
    assert resumed["topic"] == "Interrupted discussion"
    assert "participants" in message_types
    assert "need_user_turn" in message_types

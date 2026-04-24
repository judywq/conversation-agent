from typing import Iterable

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord


def get_short_term_turns(session: ConversationSession, *, limit: int = 10) -> list[TurnRecord]:
    return list(session.turns.order_by("-turn_index")[:limit][::-1])


def turns_to_messages(turns: Iterable[TurnRecord]) -> list[dict[str, str]]:
    """
    Lightweight adapter used by LLM prompt builders.
    """
    messages: list[dict[str, str]] = []
    for t in turns:
        role = "user" if t.speaker_type == TurnRecord.SPEAKER_TYPE_USER else "assistant"
        messages.append({"role": role, "content": t.utterance})
    return messages


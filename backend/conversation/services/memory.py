from typing import Iterable

from backend.conversation.models import ConversationSession
from backend.conversation.models import AgentProfile
from backend.conversation.models import TurnRecord


def get_short_term_turns(session: ConversationSession, *, limit: int = 10) -> list[TurnRecord]:
    # "Short term memory" is the previous N turns (turn_index groups), including any appendices
    # (makeshift subturns). Ordered oldest -> newest.
    if limit <= 0:
        return []

    # Iterate newest-first, collecting distinct turn_index values.
    selected_turn_indexes: list[int] = []
    for t in session.turns.order_by("-turn_index", "-subturn_index"):
        if t.turn_index not in selected_turn_indexes:
            selected_turn_indexes.append(t.turn_index)
            if len(selected_turn_indexes) >= limit:
                break

    if not selected_turn_indexes:
        return []

    selected_set = set(selected_turn_indexes)
    return list(session.turns.filter(turn_index__in=selected_set).order_by("turn_index", "subturn_index"))


def turns_to_messages(turns: Iterable[TurnRecord]) -> list[dict[str, str]]:
    """
    Lightweight adapter used by LLM prompt builders.
    """
    turns_list = list(turns)
    if not turns_list:
        return []

    session = turns_list[0].session
    # Precompute id -> display name map once.
    agent_name_map = {
        a.agent_id: (a.display_name or a.agent_id).strip()
        for a in AgentProfile.objects.filter(session=session).only("agent_id", "display_name")
    }
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    user_name = preferred or (getattr(session.user, "name", "") or "").strip() or "You"

    messages: list[dict[str, str]] = []
    for t in turns_list:
        if t.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
            speaker = user_name
        else:
            speaker = agent_name_map.get(t.speaker, t.speaker)
        messages.append({"speaker": speaker, "content": t.utterance})
    return messages


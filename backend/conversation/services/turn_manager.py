from dataclasses import dataclass
from typing import Literal

from backend.conversation.models import ConversationSession

Speaker = Literal["agent", "user", "makeshift"]


@dataclass(frozen=True)
class TurnDecision:
    terminate: bool
    next_speaker: Speaker | None
    reason: str


def should_terminate(session: ConversationSession) -> bool:
    if session.terminate:
        return True
    if session.turn_count >= session.max_turns:
        return True
    return False


def decide_next_speaker(
    session: ConversationSession,
    *,
    user_volunteered: bool,
    last_user_turn_index: int | None,
) -> TurnDecision:
    """
    Spec-aligned policy (simple v1):
    - If terminate/max turns: stop.
    - If pending_forced_user_turn: user must speak next.
    - If user volunteered: user next (but only once per volunteer signal).
    - Otherwise, default to agent.
    - If user should speak next but has not volunteered and is not forced yet,
      we route through makeshift invitation first.
    """
    if should_terminate(session):
        return TurnDecision(terminate=True, next_speaker=None, reason="termination_condition")

    if session.pending_forced_user_turn:
        return TurnDecision(terminate=False, next_speaker="user", reason="forced_user_turn")

    # User override (raise hand): prioritize giving the floor to the user.
    # We route through makeshift invitation to "appoint" the user.
    if session.user_override_requested:
        return TurnDecision(terminate=False, next_speaker="makeshift", reason="user_override_requested")

    if user_volunteered:
        return TurnDecision(terminate=False, next_speaker="user", reason="user_volunteered")

    # Heuristic: after any agent turn, invite user every 3 agent turns.
    if session.turn_count > 0 and last_user_turn_index is not None:
        if session.turn_count - last_user_turn_index >= 4:
            return TurnDecision(terminate=False, next_speaker="makeshift", reason="invite_user_periodic")

    # Default: agent speaks
    return TurnDecision(terminate=False, next_speaker="agent", reason="default_agent_turn")


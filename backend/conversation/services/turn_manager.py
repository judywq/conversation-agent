from dataclasses import dataclass
import re
from typing import Literal

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.facilitator import last_user_group_question_turn

SpeakerType = Literal["agent", "user"]

PERSONA_WEIGHTS = {
    "Discussion Driver": 0.3,
    "Fact Checker": 0.2,
    "Idea Explorer": 0.3,
    "Supportive Builder": 0.2,
    "Tense Skeptic": 0.2,
}


@dataclass(frozen=True)
class TurnDecision:
    terminate: bool
    next_speaker_type: SpeakerType | None
    next_speaker_id: str | None
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
    """
    if should_terminate(session):
        return TurnDecision(terminate=True, next_speaker_type=None, next_speaker_id=None, reason="termination_condition")

    turns_left = int(session.max_turns) - int(session.turn_count)
    if turns_left <= 1:
        closing_agent_id = _pick_any_agent(session)
        if closing_agent_id is not None:
            return TurnDecision(
                terminate=False,
                next_speaker_type="agent",
                next_speaker_id=closing_agent_id,
                reason="closing_agent_turn",
            )

    if session.pending_forced_user_turn:
        return TurnDecision(terminate=False, next_speaker_type="user", next_speaker_id="user", reason="forced_user_turn")

    # First round: do NOT generate makeshift. If the user wanted to speak first,
    # the UI already routes them to a user turn. Otherwise, let an agent open.
    if session.turn_count == 0:
        agent_id = _pick_first_agent(session)
        return TurnDecision(
            terminate=False,
            next_speaker_type="agent",
            next_speaker_id=agent_id,
            reason="first_round_agent_open",
        )

    if session.user_override_requested:
        return TurnDecision(
            terminate=False,
            next_speaker_type="user",
            next_speaker_id="user",
            reason="user_override_requested",
        )

    directive_override = _directive_target_override(session)
    if directive_override is not None:
        return directive_override

    named_question_override = _named_question_target_override(session)
    if named_question_override is not None:
        return named_question_override

    group_question_override = _user_group_question_override(session)
    if group_question_override is not None:
        return group_question_override

    if user_volunteered:
        return TurnDecision(
            terminate=False,
            next_speaker_type="user",
            next_speaker_id="user",
            reason="user_volunteered",
        )

    selected = _pick_balanced_participant(session)
    if selected == "user":
        return TurnDecision(
            terminate=False,
            next_speaker_type="user",
            next_speaker_id="user",
            reason="balanced_user_turn",
        )

    return TurnDecision(
        terminate=False,
        next_speaker_type="agent",
        next_speaker_id=selected,
        reason="balanced_agent_turn",
    )


def _pick_first_agent(session: ConversationSession) -> str | None:
    agents = list(AgentProfile.objects.filter(session=session).order_by("agent_id"))
    if not agents:
        return None
    weights = _participant_weights(agents)
    agent_weights = {a.agent_id: weights.get(a.agent_id, 0.0) for a in agents}
    return max(agent_weights.items(), key=lambda item: item[1])[0]


def _pick_any_agent(session: ConversationSession) -> str | None:
    """
    Pick an agent id that exists for this session.

    Used as a fallback for the closing-turn policy (we only need *an* agent to
    deliver the final wrap-up).
    """
    first = AgentProfile.objects.filter(session=session).order_by("agent_id").values_list("agent_id", flat=True).first()
    return str(first) if first else None


def _directive_target_override(session: ConversationSession) -> TurnDecision | None:
    """
    If the last real turn was a DIRECTIVES speech act targeted at a specific participant,
    the next speaker should be that target (so they can answer the directive).
    """
    last = (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")
        .first()
    )
    if not last:
        return None

    if str(last.speech_act or "").upper() != "DIRECTIVES":
        return None

    target = str(last.target or "").strip()
    if not target or target.lower() in {"everyone", "all"}:
        return None

    if target == "user":
        # If the directive is already addressed to the user, do NOT insert makeshift.
        return TurnDecision(
            terminate=False,
            next_speaker_type="user",
            next_speaker_id="user",
            reason="directive_target_user",
        )

    if AgentProfile.objects.filter(session=session, agent_id=target).exists():
        return TurnDecision(
            terminate=False,
            next_speaker_type="agent",
            next_speaker_id=target,
            reason="directive_target_agent",
        )
    return None


_INTERROGATIVE_START = re.compile(
    r"^(?:do|does|did|can|could|would|will|what|how|why|where|when|who|"
    r"is|are|was|were|have|has|had)\b",
    re.IGNORECASE,
)


def _last_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned[-1] if cleaned else (text or "").strip()


def _looks_interrogative(sentence: str) -> bool:
    core = (sentence or "").strip().rstrip(".!?")
    if not core:
        return False
    return bool(_INTERROGATIVE_START.match(core))


def _named_addressee_in_question(text: str, name: str) -> bool:
    nc = (name or "").strip().casefold()
    if not nc:
        return False
    u = (text or "").casefold()
    if f"{nc}?" in u or f"{nc}," in u:
        return True
    if f"{nc}." not in u:
        return False
    last = _last_sentence(text)
    return last.casefold().endswith(f"{nc}.") and _looks_interrogative(last)


def _named_question_target_override(session: ConversationSession) -> TurnDecision | None:
    """
    If the last real AGENT utterance contains a question explicitly addressed to a participant
    by DISPLAY NAME (e.g., "Judy ...?" or "Lucas?"), force the next speaker to that participant.

    This is a pragmatic fallback for when facilitator metadata doesn't mark the turn as DIRECTIVES.
    """
    last = (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")
        .first()
    )
    if not last or last.speaker_type != TurnRecord.SPEAKER_TYPE_AGENT:
        return None
    text = (last.utterance or "").strip()
    if not text:
        return None

    # Build id -> display name map
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    user_name = preferred or (getattr(session.user, "name", "") or "").strip()
    id_to_name: dict[str, str] = {"user": user_name}
    for a in AgentProfile.objects.filter(session=session).only("agent_id", "display_name"):
        id_to_name[a.agent_id] = (a.display_name or a.agent_id).strip()

    for pid, name in id_to_name.items():
        if not _named_addressee_in_question(text, name):
            continue
        if pid == "user":
            return TurnDecision(
                terminate=False,
                next_speaker_type="user",
                next_speaker_id="user",
                reason="named_question_target_user",
            )
        if AgentProfile.objects.filter(session=session, agent_id=pid).exists():
            return TurnDecision(
                terminate=False,
                next_speaker_type="agent",
                next_speaker_id=pid,
                reason="named_question_target_agent",
            )
    return None


def _user_group_question_override(session: ConversationSession) -> TurnDecision | None:
    """
    If the user just asked a question to everyone, the next speaker must be an agent
    who can answer it (never route back to the user immediately).
    """
    if last_user_group_question_turn(session) is None:
        return None
    agent_id = _pick_balanced_agent(session)
    if agent_id is None:
        return None
    return TurnDecision(
        terminate=False,
        next_speaker_type="agent",
        next_speaker_id=agent_id,
        reason="user_group_question",
    )


def _pick_balanced_agent(session: ConversationSession) -> str | None:
    agents = list(AgentProfile.objects.filter(session=session).order_by("agent_id"))
    if not agents:
        return None
    weights = _participant_weights(agents)
    counts = _participant_turn_counts(session, agents)
    agent_ids = [agent.agent_id for agent in agents]
    total = sum(counts.get(agent_id, 0) for agent_id in agent_ids)
    if total <= 0:
        return max(
            ((agent_id, weights.get(agent_id, 0.0)) for agent_id in agent_ids),
            key=lambda item: item[1],
        )[0]
    deficits = {
        agent_id: weights.get(agent_id, 0.0) - (counts.get(agent_id, 0) / total)
        for agent_id in agent_ids
    }
    return max(deficits.items(), key=lambda item: item[1])[0]


def _pick_balanced_participant(session: ConversationSession) -> str:
    agents = list(AgentProfile.objects.filter(session=session).order_by("agent_id"))
    weights = _participant_weights(agents)
    counts = _participant_turn_counts(session, agents)
    total = sum(counts.values())

    if total <= 0:
        return max(weights.items(), key=lambda item: (item[1], item[0] != "user"))[0]

    deficits = {
        participant: weights[participant] - (counts.get(participant, 0) / total)
        for participant in weights
    }
    return max(deficits.items(), key=lambda item: (item[1], item[0] == "user"))[0]


def _participant_weights(agents: list[AgentProfile]) -> dict[str, float]:
    """
    Return desired long-run share of turns per participant.

    Important: do NOT allow total agent weights to crowd the user to 0.0.
    If `agent_count` increases, raw persona weights can sum > 1; we instead
    reserve a minimum share for the user and normalize agents into the remainder.
    """
    raw_agent_weights: dict[str, float] = {}
    raw_total = 0.0
    for agent in agents:
        persona_name = str((agent.personality or {}).get("persona_name") or "")
        w = float(PERSONA_WEIGHTS.get(persona_name, 0.2))
        if w < 0:
            w = 0.0
        raw_agent_weights[agent.agent_id] = w
        raw_total += w

    # Reserve a minimum portion of turns for the user so they always get the floor,
    # but make it depend on number of participants.
    #
    # Policy: user_weight = ceil((1 / N) to nearest 0.1), where N = agents + user.
    # Examples:
    # - N=6 -> 1/6=0.166.. -> 0.2
    # - N=5 -> 1/5=0.2 -> 0.2
    # - N=4 -> 1/4=0.25 -> 0.3
    participant_count = max(1, len(raw_agent_weights) + 1)
    # Round up at the first decimal place (NOT normal rounding).
    # Equivalent to: ceil((1 / N) * 10) / 10 == ceil(10 / N) / 10
    user_floor = ((10 + participant_count - 1) // participant_count) / 10.0
    user_floor = min(0.9, max(0.1, user_floor))
    remainder = max(0.0, 1.0 - user_floor)

    if not raw_agent_weights:
        return {"user": 1.0}

    if raw_total <= 0:
        per = remainder / max(1, len(raw_agent_weights))
        normalized_agents = {aid: per for aid in raw_agent_weights}
    else:
        scale = remainder / raw_total
        normalized_agents = {aid: w * scale for aid, w in raw_agent_weights.items()}

    return {"user": user_floor, **normalized_agents}


def _participant_turn_counts(session: ConversationSession, agents: list[AgentProfile]) -> dict[str, int]:
    counts: dict[str, int] = {"user": 0}
    counts.update({agent.agent_id: 0 for agent in agents})
    turns = TurnRecord.objects.filter(session=session).exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
    for turn in turns:
        if turn.speaker_type == TurnRecord.SPEAKER_TYPE_USER:
            counts["user"] += 1
            continue
        if turn.speaker in counts:
            counts[turn.speaker] += 1
    return counts


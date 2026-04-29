from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import AgentProfile
from backend.conversation.services.turn_processor import append_turn
from backend.conversation.services.turn_processor import TurnMetadata
from backend.conversation.services.turn_processor import set_pending_forced_user_turn
from backend.conversation.services.turn_processor import set_user_override_requested

_INVITE_TEMPLATES: list[str] = [
    "{user_name}, would you like to share your thoughts next?",
    "{user_name}, what do you think about that?",
    "{user_name}, do you want to respond to that point?",
    "{user_name}, could you share your opinion on this?",
    "{user_name}, any thoughts you’d like to add?",
    "{user_name}, would you like to jump in?",
    "{user_name}, what’s your take on that?",
]


def random_choice(items: list[str]) -> str:
    import random

    return random.choice(items) if items else "Would you like to share your thoughts next?"


def _user_display_name(session: ConversationSession) -> str:
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    if preferred:
        return preferred
    name = (getattr(session.user, "name", "") or "").strip()
    return name or "You"


def _default_makeshift_speaker(session: ConversationSession) -> str:
    # Prefer the last non-makeshift turn's speaker if possible.
    last = (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")
        .first()
    )
    if last and last.speaker:
        return last.speaker

    # Otherwise, choose the highest-leadership agent (first speaker candidate).
    agents = list(AgentProfile.objects.filter(session=session))
    if agents:
        agent = max(agents, key=lambda a: float((a.traits or {}).get("leadership", 0.0)))
        return agent.agent_id

    return "user"


def invite_user(
    session: ConversationSession,
    *,
    speaker_override: str | None = None,
    utterance: str | None = None,
    audio_url: str | None = None,
) -> TurnRecord:
    previous = (speaker_override or "").strip() or (session.previous_speaker or "").strip() or _default_makeshift_speaker(session)
    # Keep `speaker` as the previous participant (for voice selection / traceability),
    # but do NOT include agent ids/numbers in the user-visible utterance text.
    if utterance is None or not str(utterance).strip():
        template = random_choice(_INVITE_TEMPLATES)
        utterance = template.format(user_name=_user_display_name(session))
    else:
        utterance = str(utterance).strip()
    processed = append_turn(
        session,
        speaker=previous,
        speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT,
        utterance=utterance,
        metadata=TurnMetadata(
            type="DIRECTIVES",
            subtype="invite",
            target="user",
            content_requirement="",
            retrieval_requirement="none",
        ),
        source="system",
        audio_url=audio_url,
    )
    # Once we issue an invitation, consume any outstanding override request.
    set_user_override_requested(processed.session, requested=False)
    set_pending_forced_user_turn(processed.session, pending=True)
    return processed.turn


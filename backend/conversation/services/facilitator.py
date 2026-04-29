import json

from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.prompts import load_facilitator_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages


ALLOWED_TAXONOMY: dict[str, list[dict[str, str]]] = {
    "ASSERTIVES": [
        {
            "subtype": "inform",
            "definition": "Provide factual or contextual information",
            "example": "The second prepcom is probably in February.",
        },
        {
            "subtype": "opinion",
            "definition": "Express a personal view or evaluation",
            "example": "I think this is such an important exercise.",
        },
        {
            "subtype": "hypothesize",
            "definition": "Propose a tentative idea or speculation",
            "example": "Maybe the Bucharest meeting will still focus on structural issues.",
        },
        {
            "subtype": "confirm",
            "definition": "Affirm or verify prior information (verifies truth / correctness of content)",
            "example": "Yeah, January.",
        },
    ],
    "DIRECTIVES": [
        {
            "subtype": "suggest",
            "definition": "Propose a course of action",
            "example": "We could take this as one part of your course performance.",
        },
        {
            "subtype": "request_info",
            "definition": "Ask for new information",
            "example": "Are there other landscape elements with symbolic value?",
        },
        {
            "subtype": "request_confirm",
            "definition": "Ask for confirmation/validation",
            "example": "Would that be okay?",
        },
        {
            "subtype": "invite",
            "definition": "Invite participation or contribution",
            "example": "Do you have any questions?",
        },
        {
            "subtype": "request_action",
            "definition": "Ask someone to perform an action",
            "example": "Could you search the information online?",
        },
        {
            "subtype": "request_permission",
            "definition": "Ask for permission to speak/act",
            "example": "Could I say something while they are thinking?",
        },
    ],
    "COMMISSIVES": [
        {
            "subtype": "offer",
            "definition": "Offer to do something",
            "example": "I'm quite willing to organise that.",
        },
        {
            "subtype": "promise",
            "definition": "Commit to a future action",
            "example": "I will give you briefing stage by stage.",
        },
        {
            "subtype": "threaten",
            "definition": "Commit to a negative consequence",
            "example": "If by February we don't know our role, I'm afraid we will have to organise an alternative conference.",
        },
    ],
    "EXPRESSIVES": [
        {
            "subtype": "agree",
            "definition": "Show agreement",
            "example": "Yeah, that's true.",
        },
        {
            "subtype": "disagree",
            "definition": "Express disagreement",
            "example": "No, I don't think that's the right way to see it.",
        },
        {
            "subtype": "acknowledge",
            "definition": "Signal understanding or receipt (signals receipt / understanding / attention)",
            "example": "Mhm, mhm.",
        },
        {
            "subtype": "thank",
            "definition": "Express gratitude",
            "example": "Thank you for an interesting presentation.",
        },
        {
            "subtype": "greet_welcome",
            "definition": "Greet or welcome participants",
            "example": "It is my great pleasure to welcome you.",
        },
        {
            "subtype": "apologize",
            "definition": "Express apology",
            "example": "I am sorry I missed that part.",
        },
    ],
    "DECLARATIONS": [
        {
            "subtype": "open_session",
            "definition": "Begin a session or activity",
            "example": "It's now time for us to continue with the programme.",
        },
        {
            "subtype": "assign_task",
            "definition": "Assign work or responsibility",
            "example": "Your task is to write a critical review of this document.",
        },
        {
            "subtype": "close_session",
            "definition": "End a session",
            "example": "Okay, we are beyond time, thank you everyone.",
        },
        {
            "subtype": "allocate_floor",
            "definition": "Give speaking rights",
            "example": "Professor, the floor is yours.",
        },
    ],
}

ALLOWED_SA: dict[str, set[str]] = {
    sa_type: {item["subtype"] for item in items}
    for sa_type, items in ALLOWED_TAXONOMY.items()
}


def coerce_speech_act_plan(payload: dict) -> dict:
    speech_act = payload.get("speech_act")
    speech_act = speech_act if isinstance(speech_act, dict) else {}
    sa_type = str(
        payload.get("type")
        or payload.get("SA_type")
        or speech_act.get("type")
        or "",
    ).upper()
    subtype = payload.get("subtype")
    if subtype is None:
        subtype = speech_act.get("subtype")
    subtype = str(subtype) if subtype is not None else None
    target = payload.get("target")
    target = str(target) if target is not None else None
    content_requirement = str(payload.get("content_requirement") or "")
    retrieval_requirement = str(
        payload.get("retrieval_requirement")
        or payload.get("retrieval need")
        or payload.get("retrieval_need")
        or "",
    )

    if sa_type not in ALLOWED_SA:
        sa_type = "ASSERTIVES"
    if subtype is not None and subtype not in ALLOWED_SA.get(sa_type, set()):
        subtype = "inform" if sa_type == "ASSERTIVES" else None

    return {
        "type": sa_type,
        "subtype": subtype,
        "target": target,
        "content_requirement": content_requirement,
        "retrieval_requirement": retrieval_requirement,
    }


def build_facilitator_plan(session: ConversationSession, *, agent: AgentProfile) -> dict:
    """
    Returns a structured plan for the next agent turn.
    """
    turns = get_short_term_turns(session, limit=3)
    context = turns_to_messages(turns)
    history = json.dumps(context, ensure_ascii=False, indent=2)
    participants = ["user", *list(session.agent_profiles.order_by("agent_id").values_list("agent_id", flat=True))]
    participants_map = _participants_name_map(session)
    directives_rate = _recent_directives_rate(session, lookback=20)
    speech_act_options = ALLOWED_TAXONOMY
    template = load_facilitator_prompt()
    next_turn_count = int(session.turn_count) + 1
    is_beginning = next_turn_count == 1
    is_ending = next_turn_count == int(session.max_turns)
    next_speaker_name = (agent.display_name or agent.agent_id).strip()
    chosen_agent_profile = {
        "agent_id": agent.agent_id,
        "display_name": next_speaker_name,
        "persona_name": str((agent.personality or {}).get("persona_name") or ""),
        "proficiency_level": str((agent.traits or {}).get("proficiency_level") or ""),
        "style": str((agent.traits or {}).get("style") or ""),
    }
    prompt_text = render_prompt_template(
        template,
        next_speaker=next_speaker_name,
        next_speaker_id=agent.agent_id,
        next_speaker_type="agent",
        turn_count=str(next_turn_count),
        max_turns=str(session.max_turns),
        is_beginning="true" if is_beginning else "false",
        is_ending="true" if is_ending else "false",
        participants=json.dumps(participants, ensure_ascii=False),
        participants_map=json.dumps(participants_map, ensure_ascii=False),
        directives_rate=f"{directives_rate:.3f}",
        agent_profile=json.dumps(chosen_agent_profile, ensure_ascii=False),
        topic=session.topic,
        history=history,
        speech_act_options=json.dumps(speech_act_options, ensure_ascii=False),
    )

    system = SystemMessage(content=prompt_text)

    llm = get_default_chat_llm()
    result = llm.invoke([system])

    raw = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            parsed = {}
    except json.JSONDecodeError:
        parsed = {}
    return coerce_speech_act_plan(parsed)


def _participants_name_map(session: ConversationSession) -> dict[str, str]:
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    user_name = preferred or (getattr(session.user, "name", "") or "").strip() or "You"
    mapping: dict[str, str] = {"user": user_name}
    for a in session.agent_profiles.order_by("agent_id"):
        mapping[a.agent_id] = (a.display_name or a.agent_id).strip()
    return mapping


def _recent_directives_rate(session: ConversationSession, *, lookback: int = 20) -> float:
    turns = (
        TurnRecord.objects.filter(session=session, speaker_type=TurnRecord.SPEAKER_TYPE_AGENT)
        .order_by("-turn_index", "-subturn_index")[:lookback]
    )
    total = 0
    directives = 0
    for t in turns:
        total += 1
        if str(t.speech_act or "").upper() == "DIRECTIVES":
            directives += 1
    if total <= 0:
        return 0.0
    return directives / total


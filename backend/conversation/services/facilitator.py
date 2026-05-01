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

# Corpus empirical proportions (major SA types).
SA_TARGET_WEIGHTS_MAJOR: dict[str, float] = {
    "ASSERTIVES": 0.74,
    "COMMISSIVES": 0.01,
    "DECLARATIONS": 0.01,
    "DIRECTIVES": 0.15,
    "EXPRESSIVES": 0.09,
}

# Conditional subtype proportions within ASSERTIVES (sum = 1.0).
SA_TARGET_WEIGHTS_ASSERTIVES_SUBTYPES: dict[str, float] = {
    "confirm": 0.03,
    "hypothesize": 0.04,
    "inform": 0.72,
    "opinion": 0.21,
}

# Conditional subtype proportions within DIRECTIVES (sum = 1.0).
SA_TARGET_WEIGHTS_DIRECTIVES_SUBTYPES: dict[str, float] = {
    "invite": 0.08,
    "request_action": 0.04,
    "request_confirm": 0.12,
    "request_info": 0.61,
    "request_permission": 0.01,
    "suggest": 0.14,
}

_GAP_EPSILON = 0.02


def _normalized_speech_act_counters(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict):
        return {"major": {}, "subtype": {"ASSERTIVES": {}, "DIRECTIVES": {}}}
    major = raw.get("major")
    if not isinstance(major, dict):
        major = {}
    subtype_root = raw.get("subtype")
    if not isinstance(subtype_root, dict):
        subtype_root = {}
    assertives_sub = subtype_root.get("ASSERTIVES")
    directives_sub = subtype_root.get("DIRECTIVES")
    if not isinstance(assertives_sub, dict):
        assertives_sub = {}
    if not isinstance(directives_sub, dict):
        directives_sub = {}
    return {
        "major": dict(major),
        "subtype": {"ASSERTIVES": dict(assertives_sub), "DIRECTIVES": dict(directives_sub)},
    }


def build_speech_act_distribution_for_prompt(session: ConversationSession) -> dict[str, str]:
    """
    Strings for facilitator template: corpus targets, raw counters, empirical rates, steering hint.
    """
    norm = _normalized_speech_act_counters(session.speech_act_counters)
    major: dict[str, int] = {k: int(v) for k, v in norm["major"].items() if isinstance(v, (int, float))}
    total_major = sum(major.values())

    subtype_root = norm["subtype"]
    assert isinstance(subtype_root, dict)
    assertives_sub = {
        k: int(v)
        for k, v in subtype_root.get("ASSERTIVES", {}).items()
        if isinstance(v, (int, float))
    }
    directives_sub = {
        k: int(v)
        for k, v in subtype_root.get("DIRECTIVES", {}).items()
        if isinstance(v, (int, float))
    }

    major_rates: dict[str, float] = {}
    if total_major > 0:
        for t in SA_TARGET_WEIGHTS_MAJOR:
            major_rates[t] = major.get(t, 0) / total_major

    assertives_total = sum(assertives_sub.values())
    directives_total = sum(directives_sub.values())

    assertives_rates: dict[str, float] = {}
    if assertives_total > 0:
        for st in SA_TARGET_WEIGHTS_ASSERTIVES_SUBTYPES:
            assertives_rates[st] = assertives_sub.get(st, 0) / assertives_total

    directives_rates: dict[str, float] = {}
    if directives_total > 0:
        for st in SA_TARGET_WEIGHTS_DIRECTIVES_SUBTYPES:
            directives_rates[st] = directives_sub.get(st, 0) / directives_total

    hint_parts: list[str] = []
    if total_major <= 0:
        hint_parts.append(
            "No classified speech acts counted yet in this session; treat corpus targets as priors when choosing type/subtype.",
        )
    else:
        under_maj = sorted(
            t
            for t, wt in SA_TARGET_WEIGHTS_MAJOR.items()
            if wt - major_rates.get(t, 0.0) > _GAP_EPSILON
        )
        if under_maj:
            hint_parts.append(
                "Major types currently below corpus share (consider steering toward): "
                + ", ".join(under_maj)
                + ".",
            )

    if assertives_total > 0:
        under_as = sorted(
            st
            for st, wt in SA_TARGET_WEIGHTS_ASSERTIVES_SUBTYPES.items()
            if wt - assertives_rates.get(st, 0.0) > _GAP_EPSILON
        )
        if under_as:
            hint_parts.append(
                "Within ASSERTIVES, subtypes below conditional corpus share: " + ", ".join(under_as) + ".",
            )

    if directives_total > 0:
        under_ds = sorted(
            st
            for st, wt in SA_TARGET_WEIGHTS_DIRECTIVES_SUBTYPES.items()
            if wt - directives_rates.get(st, 0.0) > _GAP_EPSILON
        )
        if under_ds:
            hint_parts.append(
                "Within DIRECTIVES, subtypes below conditional corpus share: " + ", ".join(under_ds) + ".",
            )

    summary_obj = {
        "major_counts": major,
        "total_classified_turns": total_major,
        "major_empirical_rates": major_rates,
        "assertives_subtype_counts": assertives_sub,
        "assertives_total": assertives_total,
        "assertives_empirical_rates_within_type": assertives_rates,
        "directives_subtype_counts": directives_sub,
        "directives_total": directives_total,
        "directives_empirical_rates_within_type": directives_rates,
        "steering_hint": " ".join(hint_parts) if hint_parts else "Distribution is close to corpus targets on recorded dimensions; choose naturally by context.",
    }

    return {
        "sa_target_weights_major": json.dumps(SA_TARGET_WEIGHTS_MAJOR, ensure_ascii=False, indent=2),
        "sa_target_weights_assertives_subtypes": json.dumps(
            SA_TARGET_WEIGHTS_ASSERTIVES_SUBTYPES,
            ensure_ascii=False,
            indent=2,
        ),
        "sa_target_weights_directives_subtypes": json.dumps(
            SA_TARGET_WEIGHTS_DIRECTIVES_SUBTYPES,
            ensure_ascii=False,
            indent=2,
        ),
        "sa_session_counts": json.dumps(norm, ensure_ascii=False, indent=2),
        "sa_session_summary": json.dumps(summary_obj, ensure_ascii=False, indent=2),
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
    sa_ctx = build_speech_act_distribution_for_prompt(session)
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
        agent_profile=json.dumps(chosen_agent_profile, ensure_ascii=False),
        topic=session.topic,
        history=history,
        speech_act_options=json.dumps(speech_act_options, ensure_ascii=False),
        **sa_ctx,
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



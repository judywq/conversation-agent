import json
import re

from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.prompts import load_facilitator_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.conversation_phase import has_unanswered_user_question
from backend.conversation.services.conversation_phase import is_winding_down_turn
from backend.conversation.services.conversation_phase import should_request_closing_agent
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.llm_tracing import invoke_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages

_FACILITATOR_CONTENT_REQUIREMENT_MAX_WORDS = 14

_PERSONAL_EXPERIENCE_KEYWORDS = (
    "personal",
    "first-person",
    "first person",
    "your experience",
    "anecdote",
    "your story",
    "share a brief",
    "from your life",
    "from your classes",
    "your dorm",
    "your campus",
    "when i ",
    "when you ",
)

_EXPERIENCE_INVITE_PHRASES = (
    "have you ever",
    "your experience",
    "what about you",
    "how about you",
    "anyone else",
    "personal story",
    "your story",
    "share your",
    "tell us about your",
    "tell me about your",
    "do you have any experience",
    "what do you all think",
    "what do you think",
)

_LIVED_EXPERIENCE_CUES = (
    "when i ",
    "my freshman",
    "my first year",
    "i remember",
    "in my dorm",
    "for me,",
    "i once",
    "personally,",
    "in my experience",
    "back in high school",
    "last semester",
)

_CAMPUS_TOPIC_CUES = (
    "dorm",
    "campus",
    "class",
    "classes",
    "club",
    "study",
    "freshman",
    "roommate",
    "university",
    "college",
)

_INTERROGATIVE_START = re.compile(
    r"^(?:do|does|did|can|could|would|will|what|how|why|where|when|who|"
    r"is|are|was|were|have|has|had)\b",
    re.IGNORECASE,
)


def last_real_turn(session: ConversationSession) -> TurnRecord | None:
    return (
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")
        .first()
    )


def _is_group_target(target: str | None) -> bool:
    cleaned = (target or "").strip().casefold()
    return not cleaned or cleaned in {"everyone", "all", "null"}


def is_interrogative_utterance(text: str) -> bool:
    utterance = (text or "").strip()
    if not utterance:
        return False
    if utterance.endswith("?"):
        return True
    parts = re.split(r"(?<=[.!?])\s+", utterance)
    parts = [part.strip() for part in parts if part.strip()]
    last = parts[-1] if parts else utterance
    core = last.rstrip(".!?").strip()
    return bool(core and _INTERROGATIVE_START.match(core))


def is_user_group_question_turn(turn: TurnRecord) -> bool:
    if turn.speaker_type != TurnRecord.SPEAKER_TYPE_USER:
        return False
    if not is_interrogative_utterance(turn.utterance):
        return False
    return _is_group_target(turn.target)


def last_user_group_question_turn(session: ConversationSession) -> TurnRecord | None:
    last = last_real_turn(session)
    if last is None or not is_user_group_question_turn(last):
        return None
    return last


def count_session_anecdotes(session: ConversationSession) -> int:
    count = 0
    turns = (
        TurnRecord.objects.filter(session=session, speaker_type=TurnRecord.SPEAKER_TYPE_AGENT)
        .only("utterance")
    )
    for turn in turns:
        text = (turn.utterance or "").casefold()
        if any(cue in text for cue in _LIVED_EXPERIENCE_CUES):
            count += 1
    return count


def detect_anecdote_opportunity(session: ConversationSession) -> bool:
    recent = list(
        TurnRecord.objects.filter(session=session)
        .exclude(speaker_type=TurnRecord.SPEAKER_TYPE_MAKESHIFT)
        .order_by("-turn_index", "-subturn_index")[:2],
    )
    if not recent:
        return False

    for turn in recent:
        text = (turn.utterance or "").casefold()
        if any(phrase in text for phrase in _EXPERIENCE_INVITE_PHRASES):
            return True
        if any(cue in text for cue in _LIVED_EXPERIENCE_CUES):
            return True

    topic = (session.topic or "").casefold()
    if count_session_anecdotes(session) == 0 and any(cue in topic for cue in _CAMPUS_TOPIC_CUES):
        if session.turn_count >= 3:
            return True
    return False


def build_experience_steering_hint(session: ConversationSession) -> str:
    last = last_real_turn(session)
    if last is not None:
        text = (last.utterance or "").casefold()
        if any(phrase in text for phrase in _EXPERIENCE_INVITE_PHRASES):
            return (
                "User invited personal sharing in the last turn; "
                "strongly prefer personal_experience: true with memory retrieval."
            )
    anecdote_count = count_session_anecdotes(session)
    if anecdote_count == 0:
        return (
            "No clear personal anecdotes from agents yet; include one when context fits "
            "(not on a fixed schedule)."
        )
    return (
        f"Session has about {anecdote_count} anecdote-style agent turn(s); "
        "reciprocal sharing still welcome when natural."
    )


def apply_experience_plan_nudge(
    session: ConversationSession,
    plan: dict,
    *,
    is_beginning: bool,
    is_ending: bool,
    is_winding_down: bool,
) -> dict:
    if is_beginning or is_ending or is_winding_down:
        return plan
    if not detect_anecdote_opportunity(session):
        return plan
    if is_personal_experience_plan(plan):
        return plan

    updated = dict(plan)
    updated["personal_experience"] = True
    updated["retrieval_requirement"] = "memory"
    updated["type"] = "ASSERTIVES"
    updated["subtype"] = "opinion"
    if not any(kw in str(updated.get("content_requirement") or "").casefold() for kw in _PERSONAL_EXPERIENCE_KEYWORDS):
        updated["content_requirement"] = clamp_facilitator_content_requirement(
            "Share a brief first-person example related to the last point.",
        )
    return updated


def apply_user_question_answer_plan(
    session: ConversationSession,
    plan: dict,
    *,
    is_ending: bool,
    is_winding_down: bool,
) -> dict:
    if is_ending and not has_unanswered_user_question(session):
        return plan
    if not has_unanswered_user_question(session) and last_user_group_question_turn(session) is None:
        return plan

    updated = dict(plan)
    updated["content_requirement"] = clamp_facilitator_content_requirement(
        "Answer the user's question directly first.",
    )
    updated["target"] = "user"
    updated["type"] = "ASSERTIVES"
    updated["subtype"] = "opinion"
    updated["personal_experience"] = False
    updated["retrieval_requirement"] = str(updated.get("retrieval_requirement") or "none")
    return updated


def finalize_facilitator_plan(
    session: ConversationSession,
    plan: dict,
    *,
    is_beginning: bool,
    is_ending: bool,
    is_winding_down: bool,
) -> dict:
    plan = apply_experience_plan_nudge(
        session,
        plan,
        is_beginning=is_beginning,
        is_ending=is_ending,
        is_winding_down=is_winding_down,
    )
    return apply_user_question_answer_plan(
        session,
        plan,
        is_ending=is_ending,
        is_winding_down=is_winding_down,
    )


def _parse_plan_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes"}
    return bool(value)


def is_personal_experience_plan(plan: dict) -> bool:
    if _parse_plan_bool(plan.get("personal_experience")):
        return True
    text = str(plan.get("content_requirement") or "").casefold()
    return any(keyword in text for keyword in _PERSONAL_EXPERIENCE_KEYWORDS)


def clamp_facilitator_content_requirement(text: str) -> str:
    """Keep facilitator instructions to one sentence and fewer than 15 words."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    parts = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)
    first_sentence = parts[0].strip() if parts else cleaned
    words = first_sentence.split()
    if len(words) <= _FACILITATOR_CONTENT_REQUIREMENT_MAX_WORDS:
        return first_sentence
    return " ".join(words[:_FACILITATOR_CONTENT_REQUIREMENT_MAX_WORDS]).rstrip(".,!?")


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
    content_requirement = clamp_facilitator_content_requirement(
        str(payload.get("content_requirement") or ""),
    )
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

    personal_experience = _parse_plan_bool(payload.get("personal_experience"))
    plan = {
        "type": sa_type,
        "subtype": subtype,
        "target": target,
        "content_requirement": content_requirement,
        "retrieval_requirement": retrieval_requirement,
        "personal_experience": personal_experience,
    }
    if is_personal_experience_plan(plan):
        plan["personal_experience"] = True
    if plan["personal_experience"] and str(plan["retrieval_requirement"] or "").strip().casefold() in {
        "",
        "none",
    }:
        plan["retrieval_requirement"] = "memory"
    return plan


def build_facilitator_plan(session: ConversationSession, *, agent: AgentProfile) -> dict:
    """
    Returns a structured plan for the next agent turn.
    """
    next_turn_count = int(session.turn_count) + 1
    is_beginning = next_turn_count == 1
    is_ending = should_request_closing_agent(session)
    is_winding_down = is_winding_down_turn(session) and not is_ending
    if is_ending or is_winding_down:
        history = build_numbered_transcript(session)
    else:
        turns = get_short_term_turns(session)
        context = turns_to_messages(turns)
        history = json.dumps(context, ensure_ascii=False, indent=2)
    participants = ["user", *list(session.agent_profiles.order_by("agent_id").values_list("agent_id", flat=True))]
    participants_map = _participants_name_map(session)
    speech_act_options = ALLOWED_TAXONOMY
    template = load_facilitator_prompt()
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
        is_winding_down="true" if is_winding_down else "false",
        experience_steering_hint=build_experience_steering_hint(session),
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
    result = invoke_chat_llm(llm, [system], user=session.user)

    raw = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            parsed = {}
    except json.JSONDecodeError:
        parsed = {}
    plan = coerce_speech_act_plan(parsed)
    return finalize_facilitator_plan(
        session,
        plan,
        is_beginning=is_beginning,
        is_ending=is_ending,
        is_winding_down=is_winding_down,
    )


def _participants_name_map(session: ConversationSession) -> dict[str, str]:
    profile = getattr(session.user, "userprofile", None)
    preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
    user_name = preferred or (getattr(session.user, "name", "") or "").strip() or "You"
    mapping: dict[str, str] = {"user": user_name}
    for a in session.agent_profiles.order_by("agent_id"):
        mapping[a.agent_id] = (a.display_name or a.agent_id).strip()
    return mapping



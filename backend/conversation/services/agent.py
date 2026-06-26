import json
import re
from dataclasses import dataclass

from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import SessionNewsChunk
from backend.conversation.prompts import load_agent_persona_prompts
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.audio_tags import filter_to_valid_audio_tags
from backend.conversation.services.audio_tags import format_audio_tags_for_prompt
from backend.conversation.services.audio_tags import strip_audio_tags
from backend.conversation.services.argument_summary import build_numbered_transcript
from backend.conversation.services.argument_summary import get_argument_summary_bullets_for_agent
from backend.conversation.services.conversation_phase import is_closing_turn
from backend.conversation.services.conversation_phase import is_winding_down_turn
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.llm_tracing import invoke_chat_llm
from backend.conversation.services.memory import get_last_speaker_utterance
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages
from backend.conversation.services.retrieval import RetrievedContext
from backend.conversation.services.retrieval import map_retrieval_sources
from backend.conversation.services.retrieval import retrieve
from backend.conversation.services.web_search import build_web_search_query
from backend.conversation.services.facilitator import is_personal_experience_plan
from backend.conversation.services.speaker_profiles import build_agent_personal_profile_context
from backend.conversation.services.user_proficiency import resolve_user_proficiency

_AGENT_RETRIEVAL_TOP_K = 5
_MAX_QUESTIONS_PER_UTTERANCE = 2
_MAX_SENTENCES_PER_UTTERANCE = 3
_MAX_SENTENCES_CLOSING = 5
_MAX_SENTENCES_WINDING_DOWN = 4
_REQUEST_LIKE_DIRECTIVE_SUBTYPES = frozenset(
    {
        "request_info",
        "request_confirm",
        "request_action",
        "request_permission",
        "invite",
    },
)
_INTERROGATIVE_START = re.compile(
    r"^(?:do|does|did|can|could|would|will|what|how|why|where|when|who|"
    r"is|are|was|were|have|has|had)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeneratedAgentUtterance:
    utterance: str
    utterance_tts: str
    retrieval_context: RetrievedContext


def _user_display_name(session: ConversationSession) -> str:
    try:
        profile = getattr(session.user, "userprofile", None)
        preferred = (
            (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
        )
    except (AttributeError, TypeError):
        preferred = ""
    if preferred:
        return preferred
    # Fallback to user.name / username.
    name = (getattr(session.user, "name", "") or "").strip()
    if name:
        return name
    return (getattr(session.user, "username", "") or "User").strip() or "User"


def _target_display_name(session: ConversationSession, target: str) -> str:
    t = (target or "").strip()
    if not t or t.lower() in {"everyone", "all", "null"}:
        return ""
    if t == "user":
        return _user_display_name(session)
    agent = session.agent_profiles.filter(agent_id=t).first()
    return (agent.display_name if agent and agent.display_name else t).strip()


def _target_type(target: str) -> str:
    t = (target or "").strip()
    if not t or t.lower() in {"everyone", "all", "null"}:
        return "everyone"
    if t == "user":
        return "user"
    return "agent"


def _is_request_like_directive(*, speech_act_type: str, speech_act_subtype: str) -> bool:
    if str(speech_act_type or "").upper() != "DIRECTIVES":
        return False
    return str(speech_act_subtype or "").lower() in _REQUEST_LIKE_DIRECTIVE_SUBTYPES


def _last_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned[-1] if cleaned else (text or "").strip()


def _looks_interrogative(sentence: str) -> bool:
    core = (sentence or "").strip().rstrip(".!?")
    if not core:
        return False
    return bool(_INTERROGATIVE_START.match(core))


def _utterance_has_question_marker(text: str) -> bool:
    if "?" in text:
        return True
    last = _last_sentence(text)
    return last.endswith(".") and _looks_interrogative(last)


def _normalize_directive_question_punctuation(
    utterance: str,
    *,
    speech_act_type: str,
    speech_act_subtype: str,
    target_display_name: str = "",
) -> str:
    text = (utterance or "").strip()
    if not text or not _is_request_like_directive(
        speech_act_type=speech_act_type,
        speech_act_subtype=speech_act_subtype,
    ):
        return text

    name = (target_display_name or "").strip()
    if name:
        period_name = re.compile(
            rf",\s*{re.escape(name)}\.$",
            flags=re.IGNORECASE,
        )
        text = period_name.sub(f", {name}?", text)

    last = _last_sentence(text)
    if last.endswith(".") and _looks_interrogative(last):
        prefix = text[: -len(last)].rstrip()
        fixed_last = last[:-1].rstrip() + "?"
        return f"{prefix} {fixed_last}".strip() if prefix else fixed_last
    return text


def _enforce_directive_target_name(
    utterance: str,
    *,
    speech_act_type: str,
    target_display_name: str,
) -> str:
    text = (utterance or "").strip()
    name = (target_display_name or "").strip()
    if not text or str(speech_act_type or "").upper() != "DIRECTIVES" or not name:
        return text

    # If the name already appears, don't add it again.
    if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
        return text

    # Only force a name when the utterance is clearly addressing the target
    # (e.g., a question/request). Otherwise, don't overuse names.
    if not _utterance_has_question_marker(text):
        return text
    # Do NOT start the utterance with the name (sounds daunting).
    # Instead, attach it naturally at the end of the (last) question.
    if text.endswith("?"):
        return text[:-1].rstrip() + f", {name}?"
    if text.endswith(".") and _looks_interrogative(_last_sentence(text)):
        return text[:-1].rstrip() + f", {name}?"
    # No dashes/em-dashes.
    return text + f", {name}"


def _limit_to_two_questions(utterance: str) -> str:
    """
    Safety clamp: keep at most two '?' in the utterance.
    This is intentionally simple; it prevents multi-question monologues.
    """
    text = (utterance or "").strip()
    if text.count("?") <= _MAX_QUESTIONS_PER_UTTERANCE:
        return text
    first = text.find("?")
    second = text.find("?", first + 1)
    if second == -1:
        return text[: first + 1].strip()
    return text[: second + 1].strip()


def _strip_dash_punctuation(utterance: str) -> str:
    """
    Remove dash-like punctuation to keep style conversational.
    """
    text = (utterance or "").strip()
    if not text:
        return text
    text = text.replace("\u2014", " ").replace("\u2013", " ").replace("-", " ")
    text = re.sub(r"\s{2,}", " ", text).strip()
    return re.sub(r"\s+([,.!?])", r"\1", text)


def _avoid_question_ending_when_not_request(
    utterance: str,
    *,
    speech_act_type: str,
    speech_act_subtype: str,
) -> str:
    """
    Only request-like DIRECTIVES should typically end with '?'.
    """
    text = (utterance or "").strip()
    if not text or not text.endswith("?"):
        return text

    t = str(speech_act_type or "").upper()
    st = str(speech_act_subtype or "").lower()
    if t != "DIRECTIVES":
        return text[:-1].rstrip() + "."

    # Keep '?' only for request-like directive subtypes.
    if st in _REQUEST_LIKE_DIRECTIVE_SUBTYPES:
        return text
    return text[:-1].rstrip() + "."


def _limit_sentences(utterance: str, *, max_sentences: int) -> str:
    text = (utterance or "").strip()
    if not text:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= max_sentences:
        return text
    return " ".join(parts[:max_sentences]).strip()


def _limit_to_three_sentences(utterance: str) -> str:
    """Safety clamp: keep at most three sentences on normal turns."""
    return _limit_sentences(utterance, max_sentences=_MAX_SENTENCES_PER_UTTERANCE)


def _max_sentences_for_turn(*, closing: bool, winding_down: bool) -> int:
    if closing:
        return _MAX_SENTENCES_CLOSING
    if winding_down:
        return _MAX_SENTENCES_WINDING_DOWN
    return _MAX_SENTENCES_PER_UTTERANCE


def _build_agent_retrieval_query(
    session: ConversationSession,
    facilitator_plan: dict,
) -> str:
    return build_web_search_query(
        topic=session.topic or "",
        content_requirement=str(facilitator_plan.get("content_requirement") or ""),
        last_speaker_line=get_last_speaker_utterance(session),
    )


def _agent_persona_name(
    facilitator_plan: dict,
    *,
    agent: AgentProfile | None = None,
) -> str:
    if agent is not None:
        return str((agent.personality or {}).get("persona_name") or "")
    return str(facilitator_plan.get("_agent_persona_name") or "")


def _should_retrieve_session_news(
    facilitator_plan: dict,
    session: ConversationSession,
) -> bool:
    has_chunks = SessionNewsChunk.objects.filter(session=session).exists()
    if not has_chunks:
        return False
    sa_type = str(facilitator_plan.get("type") or "").upper()
    sa_subtype = str(facilitator_plan.get("subtype") or "").lower()
    return sa_type == "ASSERTIVES" and sa_subtype == "inform"


def _last_completed_turn_was_user(session: ConversationSession) -> bool:
    last = session.turns.order_by("-turn_index", "-subturn_index").only("speaker_type").first()
    return last is not None and last.speaker_type == TurnRecord.SPEAKER_TYPE_USER


def resolve_agent_retrieval_sources(
    facilitator_plan: dict,
    *,
    session: ConversationSession | None = None,
    agent: AgentProfile | None = None,
) -> set[str]:
    """
    Effective retrieval sources for an agent turn (feat/rag-rules behavior).

    Always include Speech Act exemplars from the knowledge corpus. Fact Checker
    ASSERTIVES turns also get web search regardless of facilitator retrieval_need,
    except when the latest completed turn was from the user (skip web for faster reply).
    Session news is retrieved only on ASSERTIVES/inform turns when session news chunks exist.
    """
    sources = set(map_retrieval_sources(facilitator_plan.get("retrieval_requirement")))
    sources.add("exemplar")
    sa_type = str(facilitator_plan.get("type") or "").upper()
    persona_name = _agent_persona_name(facilitator_plan, agent=agent)
    if persona_name == "Fact Checker" and sa_type == "ASSERTIVES":
        sources.add("web")
    if session is not None and _should_retrieve_session_news(facilitator_plan, session):
        sources.add("news")
    if is_personal_experience_plan(facilitator_plan):
        sources |= map_retrieval_sources("memory")
    if session is not None and _last_completed_turn_was_user(session):
        sources.discard("web")
    return sources


def _build_agent_retrieval_context(
    session: ConversationSession,
    facilitator_plan: dict,
    *,
    agent: AgentProfile | None = None,
) -> RetrievedContext:
    retrieval_query = _build_agent_retrieval_query(session, facilitator_plan)
    sources = resolve_agent_retrieval_sources(
        facilitator_plan,
        session=session,
        agent=agent,
    )

    agent_slug = agent.agent_id if agent is not None else None
    return retrieve(
        retrieval_query,
        session=session,
        user=session.user,
        sources=sources,
        top_k=_AGENT_RETRIEVAL_TOP_K,
        speech_act_type=str(facilitator_plan.get("type") or ""),
        speech_act_subtype=str(facilitator_plan.get("subtype") or ""),
        agent_slug=agent_slug,
    )


def _agent_proficiency_guidance(session: ConversationSession, agent: AgentProfile) -> str:
    proficiency = resolve_user_proficiency(user=session.user)
    if proficiency["reference_utterance"]:
        return proficiency["proficiency_guidance"]
    guidance = str((agent.traits or {}).get("proficiency_guidance") or "").strip()
    if guidance:
        return guidance
    level = str((agent.traits or {}).get("proficiency_level") or proficiency["cefr_level"] or "B2")
    return f"Default proficiency: CEFR level {level}."


def generate_agent_utterance(
    session: ConversationSession,
    *,
    agent: AgentProfile,
    facilitator_plan: dict,
) -> str:
    return generate_agent_utterance_with_retrieval(
        session,
        agent=agent,
        facilitator_plan=facilitator_plan,
    ).utterance


def generate_agent_utterance_with_retrieval(
    session: ConversationSession,
    *,
    agent: AgentProfile,
    facilitator_plan: dict,
) -> GeneratedAgentUtterance:
    closing = is_closing_turn(session)
    winding_down = is_winding_down_turn(session) and not closing
    if closing or winding_down:
        history = build_numbered_transcript(session)
    else:
        turns = get_short_term_turns(session, limit=3)
        context = turns_to_messages(turns)
        history = json.dumps(context, ensure_ascii=False, indent=2)
    retrieval_plan = {
        **facilitator_plan,
        "_agent_persona_name": str((agent.personality or {}).get("persona_name") or ""),
    }
    retrieval_context = _build_agent_retrieval_context(
        session,
        retrieval_plan,
        agent=agent,
    )

    if is_personal_experience_plan(facilitator_plan):
        agent_personal_profile = build_agent_personal_profile_context(
            session.user,
            agent.agent_id,
            topic=session.topic,
        )
        personal_experience_priority = (
            "PRIORITY: This turn MUST include a brief first-person anecdote (1–2 sentences)."
        )
    else:
        agent_personal_profile = "Not applicable."
        personal_experience_priority = "Not applicable."

    persona_templates = load_agent_persona_prompts()
    selected_persona = str((agent.personality or {}).get("persona_name") or "")
    template = next(
        (p.template for p in persona_templates if p.persona_name == selected_persona),
        persona_templates[0].template,
    )
    prompt_text = render_prompt_template(
        template,
        agent_name=agent.agent_id,
        agent_display_name=(agent.display_name or agent.agent_id),
        proficiency_guidance=_agent_proficiency_guidance(session, agent),
        major=str((agent.personality or {}).get("major") or ""),
        topic=session.topic,
        history=history,
        argument_summary_bullets=get_argument_summary_bullets_for_agent(session),
        target=str(facilitator_plan.get("target") or "everyone"),
        target_type=_target_type(str(facilitator_plan.get("target") or "")),
        target_display_name=_target_display_name(
            session,
            str(facilitator_plan.get("target") or ""),
        ),
        speech_act_type=str(facilitator_plan.get("type") or "ASSERTIVES"),
        speech_act_subtype=str(facilitator_plan.get("subtype") or "inform"),
        content_requirement=str(facilitator_plan.get("content_requirement") or ""),
        agent_personal_profile=agent_personal_profile,
        retrieved_context=retrieval_context.rendered_context,
        audio_tags=format_audio_tags_for_prompt(),
        is_ending="true" if closing else "false",
        is_winding_down="true" if winding_down else "false",
        personal_experience_priority=personal_experience_priority,
    )
    system = SystemMessage(content=prompt_text)

    llm = get_default_chat_llm()
    result = invoke_chat_llm(llm, [system], user=session.user)
    text = result.content if hasattr(result, "content") else str(result)
    speech_act_type = str(facilitator_plan.get("type") or "ASSERTIVES")
    speech_act_subtype = str(facilitator_plan.get("subtype") or "")
    target_display_name = _target_display_name(
        session,
        str(facilitator_plan.get("target") or ""),
    )
    cleaned = _limit_to_two_questions(_strip_dash_punctuation(text.strip()))
    cleaned = _avoid_question_ending_when_not_request(
        cleaned,
        speech_act_type=speech_act_type,
        speech_act_subtype=speech_act_subtype,
    )
    cleaned = _limit_sentences(
        cleaned,
        max_sentences=_max_sentences_for_turn(closing=closing, winding_down=winding_down),
    )
    cleaned = _normalize_directive_question_punctuation(
        cleaned,
        speech_act_type=speech_act_type,
        speech_act_subtype=speech_act_subtype,
        target_display_name=target_display_name,
    )
    cleaned = _enforce_directive_target_name(
        cleaned,
        speech_act_type=speech_act_type,
        target_display_name=target_display_name,
    )
    return GeneratedAgentUtterance(
        utterance=strip_audio_tags(cleaned),
        utterance_tts=filter_to_valid_audio_tags(cleaned),
        retrieval_context=retrieval_context,
    )

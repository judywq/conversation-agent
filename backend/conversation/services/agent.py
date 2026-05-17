import json
import re
from dataclasses import dataclass

from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.prompts import load_agent_persona_prompts
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_last_speaker_utterance
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages
from backend.conversation.services.retrieval import RetrievedContext
from backend.conversation.services.retrieval import map_retrieval_sources
from backend.conversation.services.retrieval import retrieve
from backend.conversation.services.web_search import build_web_search_query

_AGENT_RETRIEVAL_TOP_K = 5
_MAX_QUESTIONS_PER_UTTERANCE = 2
_MAX_SENTENCES_PER_UTTERANCE = 3


@dataclass(frozen=True)
class GeneratedAgentUtterance:
    utterance: str
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
    if "?" not in text:
        return text
    # Do NOT start the utterance with the name (sounds daunting).
    # Instead, attach it naturally at the end of the (last) question.
    if text.endswith("?"):
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


def _strip_bracketed_text(utterance: str) -> str:
    """
    Remove bracketed/parenthetical fragments.
    The user explicitly doesn't want bracketed info.
    """
    text = (utterance or "").strip()
    if not text:
        return text
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    # Normalize whitespace created by deletions
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Clean stray spaces before punctuation
    return re.sub(r"\s+([,.!?])", r"\1", text)


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
    request_like = {
        "request_info",
        "request_confirm",
        "request_action",
        "request_permission",
        "invite",
    }
    if st in request_like:
        return text
    return text[:-1].rstrip() + "."


def _limit_to_three_sentences(utterance: str) -> str:
    """
    Safety clamp: keep at most three sentences.
    """
    text = (utterance or "").strip()
    if not text:
        return text
    # Split on sentence-ending punctuation while keeping the punctuation.
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= _MAX_SENTENCES_PER_UTTERANCE:
        return text
    return " ".join(parts[:_MAX_SENTENCES_PER_UTTERANCE]).strip()


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


def resolve_agent_retrieval_sources(
    facilitator_plan: dict,
    *,
    agent: AgentProfile | None = None,
) -> set[str]:
    """
    Effective retrieval sources for an agent turn (feat/rag-rules behavior).

    Always include Speech Act exemplars from the knowledge corpus. Fact Checker
    ASSERTIVES turns also get web search regardless of facilitator retrieval_need.
    """
    sources = set(map_retrieval_sources(facilitator_plan.get("retrieval_requirement")))
    sources.add("exemplar")
    sa_type = str(facilitator_plan.get("type") or "").upper()
    persona_name = _agent_persona_name(facilitator_plan, agent=agent)
    if persona_name == "Fact Checker" and sa_type == "ASSERTIVES":
        sources.add("web")
    return sources


def _build_agent_retrieval_context(
    session: ConversationSession,
    facilitator_plan: dict,
    *,
    agent: AgentProfile | None = None,
) -> RetrievedContext:
    retrieval_query = _build_agent_retrieval_query(session, facilitator_plan)
    sources = resolve_agent_retrieval_sources(facilitator_plan, agent=agent)

    return retrieve(
        retrieval_query,
        session=session,
        user=session.user,
        sources=sources,
        top_k=_AGENT_RETRIEVAL_TOP_K,
        speech_act_type=str(facilitator_plan.get("type") or ""),
        speech_act_subtype=str(facilitator_plan.get("subtype") or ""),
    )


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
    )

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
        proficiency_level=str((agent.traits or {}).get("proficiency_level") or "B2"),
        major=str((agent.personality or {}).get("major") or ""),
        topic=session.topic,
        history=history,
        target=str(facilitator_plan.get("target") or "everyone"),
        target_type=_target_type(str(facilitator_plan.get("target") or "")),
        target_display_name=_target_display_name(
            session,
            str(facilitator_plan.get("target") or ""),
        ),
        speech_act_type=str(facilitator_plan.get("type") or "ASSERTIVES"),
        speech_act_subtype=str(facilitator_plan.get("subtype") or "inform"),
        content_requirement=str(facilitator_plan.get("content_requirement") or ""),
        retrieved_context=retrieval_context.rendered_context,
    )
    system = SystemMessage(content=prompt_text)

    llm = get_default_chat_llm()
    result = llm.invoke([system])
    text = result.content if hasattr(result, "content") else str(result)
    speech_act_type = str(facilitator_plan.get("type") or "ASSERTIVES")
    speech_act_subtype = str(facilitator_plan.get("subtype") or "")
    target_display_name = _target_display_name(
        session,
        str(facilitator_plan.get("target") or ""),
    )
    cleaned = _limit_to_two_questions(
        _strip_dash_punctuation(_strip_bracketed_text(text.strip())),
    )
    cleaned = _avoid_question_ending_when_not_request(
        cleaned,
        speech_act_type=speech_act_type,
        speech_act_subtype=speech_act_subtype,
    )
    cleaned = _limit_to_three_sentences(cleaned)
    utterance = _enforce_directive_target_name(
        cleaned,
        speech_act_type=speech_act_type,
        target_display_name=target_display_name,
    )
    return GeneratedAgentUtterance(
        utterance=utterance,
        retrieval_context=retrieval_context,
    )

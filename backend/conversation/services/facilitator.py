import json

from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.prompts import PROMPT_KEY_FACILITATOR_PLAN
from backend.conversation.prompts import get_prompt_pair
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages


ALLOWED_SA: dict[str, set[str]] = {
    "ASSERTIVES": {"inform", "opinion", "hypothesize", "confirm"},
    "DIRECTIVES": {
        "suggest",
        "request_info",
        "request_confirm",
        "invite",
        "request_action",
        "request_permission",
    },
    "COMMISSIVES": {"offer", "promise", "threaten"},
    "EXPRESSIVES": {"agree", "disagree", "acknowledge", "thank", "greet_welcome", "apologize"},
    "DECLARATIONS": {"open_session", "assign_task", "close_session", "allocate_floor"},
}


def _coerce_plan(payload: dict) -> dict:
    sa_type = str(payload.get("type") or "").upper()
    subtype = payload.get("subtype")
    subtype = str(subtype) if subtype is not None else None
    target = payload.get("target")
    target = str(target) if target is not None else None
    content_requirement = str(payload.get("content_requirement") or "")
    retrieval_requirement = str(payload.get("retrieval_requirement") or "")

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
    turns = get_short_term_turns(session, limit=10)
    context = turns_to_messages(turns)

    pair = get_prompt_pair(PROMPT_KEY_FACILITATOR_PLAN)
    system = SystemMessage(content=pair.system_template)
    if pair.user_is_json_payload:
        human = HumanMessage(
            content=json.dumps(
                {
                    "topic": session.topic,
                    "agent": {
                        "agent_id": agent.agent_id,
                        "personality": agent.personality,
                        "traits": agent.traits,
                    },
                    "recent_turns": context,
                },
                ensure_ascii=False,
            ),
        )
    else:
        human = HumanMessage(
            content=pair.user_template.format(
                topic=session.topic,
                agent_id=agent.agent_id,
                personality=agent.personality,
                traits=agent.traits,
                context=context,
            ),
        )

    llm = get_default_chat_llm()
    result = llm.invoke([system, human])

    raw = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            parsed = {}
    except json.JSONDecodeError:
        parsed = {}
    return _coerce_plan(parsed)


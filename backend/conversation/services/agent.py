from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.prompts import PROMPT_KEY_AGENT_UTTERANCE
from backend.conversation.prompts import get_prompt_pair
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.memory import get_short_term_turns
from backend.conversation.services.memory import turns_to_messages


def generate_agent_utterance(
    session: ConversationSession,
    *,
    agent: AgentProfile,
    facilitator_plan: dict,
) -> str:
    turns = get_short_term_turns(session, limit=12)
    context = turns_to_messages(turns)

    persona = agent.personality or {}
    traits = agent.traits or {}
    pair = get_prompt_pair(PROMPT_KEY_AGENT_UTTERANCE)
    system = SystemMessage(
        content=pair.system_template.format(
            agent_id=agent.agent_id,
            persona=persona,
            traits=traits,
            topic=session.topic,
            facilitator_plan=facilitator_plan,
        ),
    )
    human = HumanMessage(
        content=pair.user_template.format(context=context),
    )

    llm = get_default_chat_llm()
    result = llm.invoke([system, human])
    text = result.content if hasattr(result, "content") else str(result)
    return text.strip()


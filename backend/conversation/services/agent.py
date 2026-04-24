from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
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

    system = SystemMessage(
        content=(
            "You are an AI discussion participant. Follow the Facilitator Plan strictly.\n\n"
            f"AgentId: {agent.agent_id}\n"
            f"Persona: {persona}\n"
            f"Traits: {traits}\n\n"
            f"Topic: {session.topic}\n\n"
            f"FacilitatorPlan: {facilitator_plan}\n"
        ),
    )
    human = HumanMessage(
        content=(
            "RecentTurns:\n"
            f"{context}\n\n"
            "Now produce the next utterance. Keep it concise and relevant."
        ),
    )

    llm = get_default_chat_llm()
    result = llm.invoke([system, human])
    text = result.content if hasattr(result, "content") else str(result)
    return text.strip()


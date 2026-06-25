from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from langgraph.store.base import BaseStore
from langmem import create_memory_store_manager

from backend.conversation.services.langmem_store import speaker_profile_store
from backend.conversation.services.langmem_store import speaker_profiles_enabled
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.llm_tracing import conversation_tracing_context
from backend.conversation.services.llm_tracing import invoke_runnable
from backend.conversation.services.speaker_memories import agent_profile_from_rows
from backend.conversation.services.speaker_memories import get_all_speaker_memories
from backend.conversation.services.speaker_memories import langmem_enabled
from backend.conversation.services.speaker_memories import list_memories
from backend.conversation.services.speaker_memories import relationship_profile_from_rows
from backend.conversation.services.speaker_memories import seed_agent_memories
from backend.conversation.services.speaker_memories import seed_relationship_memories
from backend.conversation.services.speaker_memories import sanitize_all_langmem_memories
from backend.conversation.services.speaker_memories import sanitize_namespace_memories
from backend.conversation.services.speaker_memories import user_profile_from_rows
from backend.conversation.services.speaker_memories import search_user_memories
from backend.conversation.services.speaker_memories import seed_user_from_userprofile
from backend.conversation.services.speaker_profile_schemas import AgentPersonalProfile
from backend.conversation.services.speaker_profile_schemas import RelationshipProfile
from backend.conversation.services.speaker_profile_schemas import SpeakerMemoryRow
from backend.conversation.services.speaker_profile_schemas import UserPersonalProfile
from backend.conversation.services.speaker_profile_schemas import agent_memories_ns
from backend.conversation.services.speaker_profile_schemas import memory_namespace_template
from backend.conversation.services.speaker_profile_schemas import relationship_memories_ns
from backend.conversation.services.speaker_profile_schemas import user_memories_ns

USER_EXTRACTION_INSTRUCTIONS = (
    "Extract durable personal facts about the human user from lines prefixed with [user]. "
    "Each row is one paraphrased sentence, never a verbatim quote. "
    "Allowed memory_type values: identity, lifestyle, preference, important_event, plan, "
    "goal_life, relationship, challenge, achievement, emotional_pattern, "
    "topic_passion, learning_goal, learning_preference, weakness, instruction. "
    "Do not store opinions, beliefs, or subjective views. "
    "Set speaker to 'user' for every row. "
    "Ignore lines prefixed with agent role slugs. "
    "Ignore temporary session topics, CEFR samples, secrets, and exact addresses."
)

AGENT_EXTRACTION_INSTRUCTIONS_TEMPLATE = (
    "Extract durable facts that agent '{agent_slug}' explicitly revealed about ITSELF. "
    "Only use utterances prefixed with [{agent_slug}]. "
    "Do NOT extract facts from [user] lines or from other agent prefixes. "
    "Allowed memory_type values: self_fact, self_preference, self_event, self_plan, "
    "self_style. Do not store opinions or beliefs. "
    "Set speaker to '{agent_slug}' for every row. "
    "One paraphrased sentence per row."
)

RELATIONSHIP_EXTRACTION_INSTRUCTIONS_TEMPLATE = (
    "Extract durable relationship facts between agent '{agent_slug}' and the user. "
    "Use [user] lines for user_to_agent rows and [{agent_slug}] lines for agent-attributed rows. "
    "Do NOT attribute other agents' lines to '{agent_slug}'. "
    "Allowed memory_type values: rapport, shared_event, shared_plan, callback, "
    "advice_given, support_moment, user_to_agent, unresolved_thread, milestone_together. "
    "Set speaker to '{agent_slug}' unless memory_type is user_to_agent (then 'user'). "
    "One paraphrased sentence per row."
)


@dataclass(frozen=True)
class SpeakerProfileBundle:
    user: UserPersonalProfile | None
    agent: AgentPersonalProfile | None
    relationship: RelationshipProfile | None

    def format_for_prompt(self) -> str:
        sections: list[str] = []
        if self.user is not None:
            sections.append(f"User profile:\n{self.user.model_dump_json(indent=2)}")
        if self.relationship is not None:
            sections.append(
                f"Your relationship with this user:\n{self.relationship.model_dump_json(indent=2)}",
            )
        if self.agent is not None:
            sections.append(
                f"Your own remembered persona details:\n{self.agent.model_dump_json(indent=2)}",
            )
        return "\n\n".join(sections) if sections else ""


def _langmem_config(user_id: int | str, agent_slug: str | None = None) -> dict[str, Any]:
    configurable: dict[str, Any] = {"user_id": str(user_id)}
    if agent_slug is not None:
        configurable["agent_slug"] = agent_slug
    return {"configurable": configurable}


def _user_memory_manager(store: BaseStore):
    return create_memory_store_manager(
        get_default_chat_llm(),
        namespace=memory_namespace_template("user"),
        schemas=[SpeakerMemoryRow],
        instructions=USER_EXTRACTION_INSTRUCTIONS,
        enable_inserts=True,
        store=store,
    )


def _agent_memory_manager(store: BaseStore, agent_slug: str):
    return create_memory_store_manager(
        get_default_chat_llm(),
        namespace=memory_namespace_template("agent"),
        schemas=[SpeakerMemoryRow],
        instructions=AGENT_EXTRACTION_INSTRUCTIONS_TEMPLATE.format(agent_slug=agent_slug),
        enable_inserts=True,
        store=store,
    )


def _relationship_memory_manager(store: BaseStore, agent_slug: str):
    return create_memory_store_manager(
        get_default_chat_llm(),
        namespace=memory_namespace_template("relationship"),
        schemas=[SpeakerMemoryRow],
        instructions=RELATIONSHIP_EXTRACTION_INSTRUCTIONS_TEMPLATE.format(agent_slug=agent_slug),
        enable_inserts=True,
        store=store,
    )


def get_user_profile(user: Any, *, store: BaseStore | None = None) -> UserPersonalProfile | None:
    if not langmem_enabled():
        return None
    with speaker_profile_store(store) as active_store:
        rows = list_memories(active_store, user_memories_ns(user.id))
        if not rows:
            return None
        return user_profile_from_rows(rows)


def get_agent_profile(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> AgentPersonalProfile | None:
    if not langmem_enabled():
        return None
    with speaker_profile_store(store) as active_store:
        rows = list_memories(active_store, agent_memories_ns(user.id, agent_slug))
        if not rows:
            return None
        return agent_profile_from_rows(agent_slug, rows)


def get_relationship_profile(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> RelationshipProfile | None:
    if not langmem_enabled():
        return None
    with speaker_profile_store(store) as active_store:
        rows = list_memories(active_store, relationship_memories_ns(user.id, agent_slug))
        if not rows:
            return None
        return relationship_profile_from_rows(agent_slug, rows)


def format_profiles_for_prompt(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> SpeakerProfileBundle:
    return SpeakerProfileBundle(
        user=get_user_profile(user, store=store),
        agent=get_agent_profile(user, agent_slug, store=store),
        relationship=get_relationship_profile(user, agent_slug, store=store),
    )


def build_agent_personal_profile_context(
    user: Any,
    agent_slug: str,
    *,
    topic: str = "",
    store: BaseStore | None = None,
) -> str:
    if not langmem_enabled():
        return (
            "No stored personal profile available. "
            "You may invent one brief plausible first-person detail consistent with your persona and major."
        )

    profile = get_agent_profile(user, agent_slug, store=store)
    lines: list[str] = []
    if profile is not None:
        if profile.persona_summary:
            lines.append(f"Persona: {profile.persona_summary}")
        if profile.speaking_style:
            lines.append(f"Speaking style: {profile.speaking_style}")
        for fact in profile.self_revealed_facts:
            cleaned = str(fact).strip()
            if cleaned:
                lines.append(f"- {cleaned}")

    topic_query = str(topic or "").strip()
    if topic_query:
        hits = search_user_memories(
            user,
            topic_query,
            agent_slug=agent_slug,
            top_k=5,
            store=store,
        )
        agent_namespace = agent_memories_ns(user.id, agent_slug)
        seen = {line.casefold() for line in lines}
        for row, _score, namespace in hits:
            if namespace != agent_namespace:
                continue
            if row.memory_type not in {
                "self_fact",
                "self_event",
                "self_preference",
                "self_plan",
                "self_style",
            }:
                continue
            content = str(row.content or "").strip()
            if not content:
                continue
            line = f"- [{row.memory_type}] {content}"
            if line.casefold() in seen:
                continue
            lines.append(line)
            seen.add(line.casefold())

    if not lines:
        return (
            "No personal anecdotes on file for this agent yet. "
            "You may invent one brief plausible first-person example aligned with your persona, major, and the topic."
        )
    return "Reuse these personal details if relevant; do not contradict them:\n" + "\n".join(lines)


def seed_user_profile_from_userprofile(user: Any, *, store: BaseStore | None = None) -> UserPersonalProfile:
    return seed_user_from_userprofile(user, store=store)


def seed_agent_profile(
    user: Any,
    agent_slug: str,
    *,
    display_name: str = "",
    persona_name: str = "",
    persona_summary: str = "",
    speaking_style: str = "",
    store: BaseStore | None = None,
) -> AgentPersonalProfile:
    return seed_agent_memories(
        user,
        agent_slug,
        display_name=display_name,
        persona_name=persona_name,
        persona_summary=persona_summary,
        speaking_style=speaking_style,
        store=store,
    )


def seed_relationship_profile(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> RelationshipProfile:
    return seed_relationship_memories(user, agent_slug, store=store)


def extract_and_update_profiles(
    user: Any,
    messages: list[dict[str, str]],
    *,
    agent_slug: str | None = None,
    store: BaseStore | None = None,
) -> None:
    if not langmem_enabled():
        return
    if not messages:
        return
    if settings.FAKE_LLM_REQUEST:
        return
    if not getattr(settings, "LANGMEM_PROFILE_EXTRACTION_ENABLED", True):
        return
    config = _langmem_config(user.id, agent_slug)
    payload = {"messages": messages}
    with speaker_profile_store(store) as active_store:
        if agent_slug:
            agent_ns = agent_memories_ns(user.id, agent_slug)
            relationship_ns = relationship_memories_ns(user.id, agent_slug)
            invoke_runnable(_agent_memory_manager(active_store, agent_slug), payload, user=user, config=config)
            invoke_runnable(
                _relationship_memory_manager(active_store, agent_slug),
                payload,
                user=user,
                config=config,
            )
            sanitize_namespace_memories(active_store, agent_ns)
            sanitize_namespace_memories(active_store, relationship_ns)
        else:
            user_ns = user_memories_ns(user.id)
            invoke_runnable(_user_memory_manager(active_store), payload, user=user, config=config)
            sanitize_namespace_memories(active_store, user_ns)


def dump_all_profiles(user: Any, *, store: BaseStore | None = None) -> dict[str, Any]:
    if not speaker_profiles_enabled():
        return {"enabled": False, "profiles": {}}
    return get_all_speaker_memories(user, store=store)

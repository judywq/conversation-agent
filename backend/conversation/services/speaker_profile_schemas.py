from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class UserPersonalProfile(BaseModel):
    preferred_name: str | None = None
    major: str | None = None
    cefr_level: str | None = None
    interests: list[str] = Field(default_factory=list)
    learning_goals: list[str] = Field(default_factory=list)
    communication_style: str | None = None
    recurring_topics: list[str] = Field(default_factory=list)
    notable_events: list[str] = Field(default_factory=list)


class AgentPersonalProfile(BaseModel):
    agent_slug: str | None = None
    display_name: str | None = None
    persona_name: str | None = None
    persona_summary: str | None = None
    speaking_style: str | None = None
    memorable_traits: list[str] = Field(default_factory=list)
    self_revealed_facts: list[str] = Field(default_factory=list)


class RelationshipProfile(BaseModel):
    agent_slug: str | None = None
    rapport_level: str | None = None
    shared_history: list[str] = Field(default_factory=list)
    how_agent_views_user: str | None = None
    topics_discussed_together: list[str] = Field(default_factory=list)
    personal_callbacks: list[str] = Field(default_factory=list)
    last_interaction_summary: str | None = None


USER_MEMORY_TYPES = frozenset(
    {
        "identity",
        "lifestyle",
        "preference",
        "important_event",
        "plan",
        "goal_life",
        "relationship",
        "challenge",
        "achievement",
        "emotional_pattern",
        "topic_passion",
        "learning_goal",
        "learning_preference",
        "weakness",
        "instruction",
    },
)
AGENT_MEMORY_TYPES = frozenset(
    {
        "self_fact",
        "self_preference",
        "self_event",
        "self_plan",
        "self_style",
    },
)
BLOCKED_MEMORY_TYPES = frozenset({"opinion", "self_opinion"})
USER_ATTRIBUTED_RELATIONSHIP_TYPES = frozenset({"user_to_agent"})
RELATIONSHIP_MEMORY_TYPES = frozenset(
    {
        "rapport",
        "shared_event",
        "shared_plan",
        "callback",
        "advice_given",
        "support_moment",
        "user_to_agent",
        "unresolved_thread",
        "milestone_together",
    },
)
ALL_MEMORY_TYPES = USER_MEMORY_TYPES | AGENT_MEMORY_TYPES | RELATIONSHIP_MEMORY_TYPES
EXTRACTABLE_MEMORY_TYPES = ALL_MEMORY_TYPES - BLOCKED_MEMORY_TYPES

MemoryNamespaceKind = Literal["user", "agent", "relationship"]

PROFILE_STORE_KEY = "default"


LANGMEM_ROW_KIND = "SpeakerMemoryRow"


class SpeakerMemoryRow(BaseModel):
    memory_type: str
    content: str
    confidence: float = 1.0
    speaker: str = "user"
    source_label: str = "conversation"
    metadata: dict[str, Any] = Field(default_factory=dict)


def user_memories_ns(user_id: int | str) -> tuple[str, ...]:
    return ("users", str(user_id), "memories")


def learner_memories_ns(user_id: int | str) -> tuple[str, ...]:
    """Deprecated alias for :func:`user_memories_ns`."""
    return user_memories_ns(user_id)


def agent_memories_ns(user_id: int | str, agent_slug: str) -> tuple[str, ...]:
    return ("users", str(user_id), "agents", agent_slug, "memories")


def relationship_memories_ns(user_id: int | str, agent_slug: str) -> tuple[str, ...]:
    return ("users", str(user_id), "agents", agent_slug, "relationship")


def user_profile_ns(user_id: int | str) -> tuple[str, ...]:
    return user_memories_ns(user_id)


def agent_self_ns(user_id: int | str, agent_slug: str) -> tuple[str, ...]:
    return agent_memories_ns(user_id, agent_slug)


def relationship_ns(user_id: int | str, agent_slug: str) -> tuple[str, ...]:
    return relationship_memories_ns(user_id, agent_slug)


def memory_namespace_template(kind: MemoryNamespaceKind) -> tuple[str, ...]:
    if kind == "user":
        return ("users", "{user_id}", "memories")
    if kind == "agent":
        return ("users", "{user_id}", "agents", "{agent_slug}", "memories")
    if kind == "relationship":
        return ("users", "{user_id}", "agents", "{agent_slug}", "relationship")
    raise ValueError(f"Unknown memory namespace kind: {kind}")


def profile_namespace_template(kind: str) -> tuple[str, ...]:
    if kind == "user":
        return memory_namespace_template("user")
    if kind == "agent":
        return memory_namespace_template("agent")
    if kind == "relationship":
        return memory_namespace_template("relationship")
    raise ValueError(f"Unknown profile kind: {kind}")


def profile_to_store_value(profile: BaseModel) -> dict[str, Any]:
    return profile.model_dump(mode="json")
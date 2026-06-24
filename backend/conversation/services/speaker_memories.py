from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from typing import Iterator

from django.conf import settings
from langgraph.store.base import BaseStore

from backend.conversation.services.langmem_store import speaker_profile_store
from backend.conversation.services.langmem_store import speaker_profiles_enabled
from backend.conversation.services.speaker_profile_schemas import BLOCKED_MEMORY_TYPES
from backend.conversation.services.speaker_profile_schemas import LANGMEM_ROW_KIND
from backend.conversation.services.speaker_profile_schemas import AgentPersonalProfile
from backend.conversation.services.speaker_profile_schemas import RelationshipProfile
from backend.conversation.services.speaker_profile_schemas import SpeakerMemoryRow
from backend.conversation.services.speaker_profile_schemas import UserPersonalProfile
from backend.conversation.services.speaker_profile_schemas import USER_ATTRIBUTED_RELATIONSHIP_TYPES
from backend.conversation.services.speaker_profile_schemas import agent_memories_ns
from backend.conversation.services.speaker_profile_schemas import user_memories_ns
from backend.conversation.services.speaker_profile_schemas import relationship_memories_ns

logger = logging.getLogger(__name__)


def langmem_enabled() -> bool:
    return bool(
        speaker_profiles_enabled()
        and getattr(settings, "LANGMEM_ENABLED", True)
    )


def memory_row_key(row: SpeakerMemoryRow) -> str:
    raw = f"{row.memory_type}:{row.content}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _store_value_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _is_langmem_wrapped_payload(payload: dict[str, Any]) -> bool:
    return "kind" in payload and "content" in payload


def unwrap_store_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if _is_langmem_wrapped_payload(payload):
        content = payload.get("content")
        return content if isinstance(content, dict) else None
    if "memory_type" in payload:
        return payload
    return None


def wrap_row_for_store(row: SpeakerMemoryRow) -> dict[str, Any]:
    return {
        "kind": LANGMEM_ROW_KIND,
        "content": row.model_dump(mode="json"),
    }


def _normalize_content_key(content: str) -> str:
    return " ".join((content or "").casefold().split())


def expected_speaker(
    *,
    namespace_kind: str,
    agent_slug: str | None,
    memory_type: str,
) -> str | None:
    if namespace_kind == "user":
        return "user"
    if namespace_kind == "agent" and agent_slug:
        return agent_slug
    if namespace_kind == "relationship" and agent_slug:
        if memory_type in USER_ATTRIBUTED_RELATIONSHIP_TYPES:
            return "user"
        return agent_slug
    return None


def is_valid_speaker(
    row: SpeakerMemoryRow,
    *,
    namespace_kind: str,
    agent_slug: str | None,
) -> bool:
    expected = expected_speaker(
        namespace_kind=namespace_kind,
        agent_slug=agent_slug,
        memory_type=row.memory_type,
    )
    if expected is None:
        return False
    speaker = (row.speaker or "").strip()
    return speaker == expected


def normalize_memory_row(
    row: SpeakerMemoryRow,
    *,
    namespace_kind: str,
    agent_slug: str | None,
) -> SpeakerMemoryRow | None:
    speaker = (row.speaker or "").strip()
    if not speaker:
        expected = expected_speaker(
            namespace_kind=namespace_kind,
            agent_slug=agent_slug,
            memory_type=row.memory_type,
        )
        if expected is None:
            return None
        row = row.model_copy(update={"speaker": expected})
    if not is_valid_speaker(row, namespace_kind=namespace_kind, agent_slug=agent_slug):
        return None
    return row


def _namespace_context(namespace: tuple[str, ...]) -> dict[str, Any]:
    return parse_namespace_metadata(namespace)


def delete_memory(
    store: BaseStore,
    namespace: tuple[str, ...],
    key: str,
) -> None:
    store.delete(namespace, key)


def _user_memory_content_keys(store: BaseStore, user_id: int | str) -> set[str]:
    keys: set[str] = set()
    for row in list_memories(store, user_memories_ns(user_id), limit=500):
        keys.add(_normalize_content_key(row.content))
    return keys


def sanitize_namespace_memories(
    store: BaseStore,
    namespace: tuple[str, ...],
) -> tuple[int, int]:
    """Delete blocked memory types and rows with invalid speaker attribution."""
    context = _namespace_context(namespace)
    namespace_kind = str(context["namespace_kind"])
    agent_slug = context["agent_slug"]
    user_id = context["user_id"]
    deleted = 0
    updated = 0
    user_content_keys: set[str] | None = None
    if namespace_kind == "agent" and user_id is not None:
        user_content_keys = _user_memory_content_keys(store, user_id)
    for item in _iter_store_items(store, namespace, limit=500):
        row = _item_to_row(item)
        if row is None:
            continue
        store_key = str(getattr(item, "key", "") or memory_row_key(row))
        if row.memory_type in BLOCKED_MEMORY_TYPES:
            delete_memory(store, namespace, store_key)
            deleted += 1
            continue
        if (
            namespace_kind == "agent"
            and user_content_keys is not None
            and _normalize_content_key(row.content) in user_content_keys
        ):
            delete_memory(store, namespace, store_key)
            deleted += 1
            continue
        normalized = normalize_memory_row(
            row,
            namespace_kind=namespace_kind,
            agent_slug=agent_slug,
        )
        if normalized is None:
            delete_memory(store, namespace, store_key)
            deleted += 1
            continue
        if normalized.speaker != row.speaker:
            put_memory(store, namespace, normalized, key=store_key)
            updated += 1
    return deleted, updated


def sanitize_all_langmem_memories(*, store: BaseStore | None = None) -> dict[str, int]:
    totals = {"deleted": 0, "updated": 0, "namespaces": 0}
    with speaker_profile_store(store) as active_store:
        try:
            namespaces = active_store.list_namespaces(prefix=("users",), limit=500)
        except Exception:
            logger.exception("LangMem sanitize failed to list namespaces.")
            return totals
        for namespace in namespaces:
            deleted, updated = sanitize_namespace_memories(active_store, namespace)
            if deleted or updated:
                totals["namespaces"] += 1
            totals["deleted"] += deleted
            totals["updated"] += updated
    return totals


def _row_is_allowed(row: SpeakerMemoryRow) -> bool:
    return row.memory_type not in BLOCKED_MEMORY_TYPES


def _item_to_row(item: Any) -> SpeakerMemoryRow | None:
    if item is None:
        return None
    payload = _store_value_to_dict(getattr(item, "value", item))
    if payload is None:
        return None
    row_payload = unwrap_store_payload(payload)
    if row_payload is None:
        return None
    try:
        return SpeakerMemoryRow.model_validate(row_payload)
    except Exception:
        logger.debug("Skipping invalid LangMem row payload", exc_info=True)
        return None


def put_memory(
    store: BaseStore,
    namespace: tuple[str, ...],
    row: SpeakerMemoryRow,
    *,
    key: str | None = None,
) -> str:
    if row.memory_type in BLOCKED_MEMORY_TYPES:
        raise ValueError(f"Blocked LangMem memory_type: {row.memory_type}")
    context = _namespace_context(namespace)
    original_speaker = row.speaker
    normalized = normalize_memory_row(
        row,
        namespace_kind=str(context["namespace_kind"]),
        agent_slug=context["agent_slug"],
    )
    if normalized is None:
        raise ValueError(
            f"Invalid speaker {original_speaker!r} for namespace {namespace}",
        )
    row = normalized
    store_key = key or memory_row_key(row)
    store.put(namespace, store_key, wrap_row_for_store(row))
    return store_key


def migrate_legacy_langmem_rows(*, store: BaseStore | None = None) -> int:
    """Re-wrap flat SpeakerMemoryRow payloads into LangMem's {kind, content} format."""
    if not langmem_enabled():
        return 0
    migrated = 0
    with speaker_profile_store(store) as active_store:
        try:
            namespaces = active_store.list_namespaces(prefix=("users",), limit=500)
        except Exception:
            logger.exception("LangMem legacy migration failed to list namespaces.")
            return 0
        for namespace in namespaces:
            try:
                items = list(_iter_store_items(active_store, namespace, limit=500))
            except Exception:
                logger.debug("LangMem legacy migration skipped namespace %s", namespace, exc_info=True)
                continue
            for item in items:
                payload = _store_value_to_dict(getattr(item, "value", item))
                if payload is None or _is_langmem_wrapped_payload(payload):
                    continue
                row_payload = unwrap_store_payload(payload)
                if row_payload is None:
                    continue
                try:
                    row = SpeakerMemoryRow.model_validate(row_payload)
                except Exception:
                    continue
                store_key = str(getattr(item, "key", "") or memory_row_key(row))
                put_memory(active_store, namespace, row, key=store_key)
                migrated += 1
    if migrated:
        logger.info("Migrated %s legacy LangMem rows to wrapped store format.", migrated)
    return migrated


def list_memories(
    store: BaseStore,
    namespace: tuple[str, ...],
    *,
    limit: int = 100,
) -> list[SpeakerMemoryRow]:
    rows: list[SpeakerMemoryRow] = []
    try:
        results = store.search(namespace, limit=limit)
    except Exception:
        logger.debug("LangMem list_memories search failed", exc_info=True)
        return rows
    for item in results:
        row = _item_to_row(item)
        if row is not None and _row_is_allowed(row):
            rows.append(row)
    return rows


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", (text or "").casefold()) if len(token) >= 2]


def _keyword_score(query_terms: list[str], row: SpeakerMemoryRow) -> float:
    haystack = " ".join(
        [row.content, row.memory_type, row.source_label, json.dumps(row.metadata, default=str)],
    ).casefold()
    return float(sum(1 for term in query_terms if term in haystack))


def search_memories(
    store: BaseStore,
    namespace: tuple[str, ...],
    query: str,
    *,
    limit: int = 5,
) -> list[tuple[SpeakerMemoryRow, float]]:
    q = (query or "").strip()
    if not q:
        return []

    try:
        results = store.search(namespace, query=q, limit=limit)
        rows: list[tuple[SpeakerMemoryRow, float]] = []
        for index, item in enumerate(results):
            row = _item_to_row(item)
            if row is None or not _row_is_allowed(row):
                continue
            score = getattr(item, "score", None)
            rows.append((row, float(score) if score is not None else float(limit - index)))
        if rows:
            return rows
    except TypeError:
        pass
    except Exception:
        logger.debug("LangMem vector search failed; falling back to keyword", exc_info=True)

    terms = _tokenize(q)
    if not terms:
        return []
    scored: list[tuple[float, SpeakerMemoryRow]] = []
    for row in list_memories(store, namespace, limit=max(limit * 4, 20)):
        if not _row_is_allowed(row):
            continue
        score = _keyword_score(terms, row)
        if score <= 0:
            continue
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(row, score) for score, row in scored[:limit]]


def list_agent_slugs(store: BaseStore, user_id: int | str) -> list[str]:
    prefix = ("users", str(user_id), "agents")
    try:
        namespaces = store.list_namespaces(prefix=prefix, limit=100)
    except Exception:
        logger.debug("LangMem list_agent_slugs failed", exc_info=True)
        return []
    slugs: set[str] = set()
    for namespace in namespaces:
        if len(namespace) >= 4 and namespace[2] == "agents":
            slugs.add(str(namespace[3]))
    return sorted(slugs)


def search_user_memories(
    user: Any,
    query: str,
    *,
    agent_slug: str | None = None,
    top_k: int = 5,
    store: BaseStore | None = None,
) -> list[tuple[SpeakerMemoryRow, float, tuple[str, ...]]]:
    if not langmem_enabled():
        return []
    namespaces: list[tuple[str, ...]] = [user_memories_ns(user.id)]
    if agent_slug:
        namespaces.extend(
            [
                agent_memories_ns(user.id, agent_slug),
                relationship_memories_ns(user.id, agent_slug),
            ],
        )
    per_ns = max(1, top_k // len(namespaces) + 1)
    merged: list[tuple[SpeakerMemoryRow, float, tuple[str, ...]]] = []
    with speaker_profile_store(store) as active_store:
        for namespace in namespaces:
            for row, score in search_memories(active_store, namespace, query, limit=per_ns):
                merged.append((row, score, namespace))
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged[:top_k]


def get_all_speaker_memories(user: Any, *, store: BaseStore | None = None) -> dict[str, Any]:
    if not langmem_enabled():
        return {"enabled": False, "user_id": getattr(user, "id", None), "memories": {}}
    payload: dict[str, Any] = {"enabled": True, "user_id": user.id, "memories": {}}
    with speaker_profile_store(store) as active_store:
        prefix = ("users", str(user.id))
        try:
            namespaces = active_store.list_namespaces(prefix=prefix, limit=200)
        except Exception:
            namespaces = [user_memories_ns(user.id)]
        for namespace in namespaces:
            key = "/".join(namespace)
            rows = list_memories(active_store, namespace, limit=100)
            if rows:
                payload["memories"][key] = [row.model_dump(mode="json") for row in rows]
    return payload


def _profile_field_from_rows(rows: list[SpeakerMemoryRow], field: str) -> str | None:
    for row in rows:
        meta = row.metadata if isinstance(row.metadata, dict) else {}
        if meta.get("field") == field:
            value = meta.get("value")
            if value not in (None, ""):
                return str(value)
    return None


def user_profile_from_rows(rows: list[SpeakerMemoryRow]) -> UserPersonalProfile:
    profile = UserPersonalProfile(
        preferred_name=_profile_field_from_rows(rows, "preferred_name"),
        major=_profile_field_from_rows(rows, "major"),
        cefr_level=_profile_field_from_rows(rows, "cefr_level"),
    )
    ocean = _profile_field_from_rows(rows, "ocean")
    if ocean:
        profile.communication_style = ocean
    for row in rows:
        if row.memory_type == "learning_goal" and row.content:
            profile.learning_goals.append(row.content)
        if row.memory_type == "topic_passion" and row.content:
            profile.interests.append(row.content)
    return profile


def agent_profile_from_rows(agent_slug: str, rows: list[SpeakerMemoryRow]) -> AgentPersonalProfile:
    profile = AgentPersonalProfile(agent_slug=agent_slug)
    self_memory_types = {"self_fact", "self_event", "self_preference", "self_plan"}
    for row in rows:
        meta = row.metadata if isinstance(row.metadata, dict) else {}
        field = meta.get("field")
        value = meta.get("value")
        if field == "display_name" and value:
            profile.display_name = str(value)
        elif field == "persona_name" and value:
            profile.persona_name = str(value)
        elif field == "persona_summary" and value:
            profile.persona_summary = str(value)
        elif field == "speaking_style" and value:
            profile.speaking_style = str(value)
        elif row.memory_type == "self_style" and row.content and not profile.speaking_style:
            profile.speaking_style = row.content
        elif row.memory_type in self_memory_types and row.content:
            profile.self_revealed_facts.append(row.content)
    return profile


def relationship_profile_from_rows(agent_slug: str, rows: list[SpeakerMemoryRow]) -> RelationshipProfile:
    profile = RelationshipProfile(agent_slug=agent_slug)
    for row in rows:
        meta = row.metadata if isinstance(row.metadata, dict) else {}
        if meta.get("field") == "rapport_level" and meta.get("value"):
            profile.rapport_level = str(meta.get("value"))
        elif meta.get("field") == "last_interaction_summary" and meta.get("value"):
            profile.last_interaction_summary = str(meta.get("value"))
        elif row.memory_type == "shared_event" and row.content:
            profile.shared_history.append(row.content)
        elif row.memory_type == "callback" and row.content:
            profile.personal_callbacks.append(row.content)
    return profile


def seed_user_from_userprofile(user: Any, *, store: BaseStore | None = None) -> UserPersonalProfile:
    profile_model = getattr(user, "userprofile", None)
    ocean_summary = ""
    if profile_model is not None:
        ocean = profile_model.ocean if isinstance(profile_model.ocean, dict) else {}
        if ocean:
            ocean_summary = ", ".join(f"{k}={v}" for k, v in sorted(ocean.items()))
    preferred_name = (getattr(profile_model, "preferred_name", "") or "").strip()
    major = (getattr(profile_model, "major", "") or "").strip()
    cefr_level = (getattr(profile_model, "cefr_level", "") or "").strip().upper()
    reference_utterance = (getattr(profile_model, "proficiency_reference_utterance", "") or "").strip()
    profile = UserPersonalProfile(
        preferred_name=preferred_name or None,
        major=major or None,
        cefr_level=cefr_level or None,
        communication_style=ocean_summary or None,
    )
    if not langmem_enabled():
        return profile
    rows: list[SpeakerMemoryRow] = []
    if preferred_name:
        rows.append(
            SpeakerMemoryRow(
                memory_type="identity",
                content=f"The user prefers to be called {preferred_name}.",
                speaker="user",
                source_label="profile_sync",
                metadata={"field": "preferred_name", "value": preferred_name},
            ),
        )
    if major:
        rows.append(
            SpeakerMemoryRow(
                memory_type="identity",
                content=f"The user's major is {major}.",
                speaker="user",
                source_label="profile_sync",
                metadata={"field": "major", "value": major},
            ),
        )
    if reference_utterance:
        rows.append(
            SpeakerMemoryRow(
                memory_type="learning_goal",
                content=(
                    "The user's English speaking level is best represented by this reference "
                    f'utterance: "{reference_utterance}"'
                ),
                speaker="user",
                source_label="profile_sync",
                metadata={"field": "proficiency_reference_utterance", "value": reference_utterance},
            ),
        )
    elif cefr_level:
        rows.append(
            SpeakerMemoryRow(
                memory_type="learning_goal",
                content=f"The user's current CEFR level is {cefr_level}.",
                speaker="user",
                source_label="profile_sync",
                metadata={"field": "cefr_level", "value": cefr_level},
            ),
        )
    if ocean_summary:
        rows.append(
            SpeakerMemoryRow(
                memory_type="preference",
                content=f"The user's OCEAN personality summary is {ocean_summary}.",
                speaker="user",
                source_label="profile_sync",
                metadata={"field": "ocean", "value": ocean_summary},
            ),
        )
    namespace = user_memories_ns(user.id)
    with speaker_profile_store(store) as active_store:
        for row in rows:
            put_memory(active_store, namespace, row)
    return profile


def seed_agent_memories(
    user: Any,
    agent_slug: str,
    *,
    display_name: str = "",
    persona_name: str = "",
    persona_summary: str = "",
    speaking_style: str = "",
    store: BaseStore | None = None,
) -> AgentPersonalProfile:
    profile = AgentPersonalProfile(
        agent_slug=agent_slug,
        display_name=display_name or None,
        persona_name=persona_name or None,
        persona_summary=persona_summary or None,
        speaking_style=speaking_style or None,
    )
    if not langmem_enabled():
        return profile
    rows: list[SpeakerMemoryRow] = []
    if display_name:
        rows.append(
            SpeakerMemoryRow(
                memory_type="self_fact",
                content=f"This agent's display name is {display_name}.",
                speaker=agent_slug,
                source_label="profile_seed",
                metadata={"field": "display_name", "value": display_name},
            ),
        )
    if persona_name:
        rows.append(
            SpeakerMemoryRow(
                memory_type="self_fact",
                content=f"This agent's persona name is {persona_name}.",
                speaker=agent_slug,
                source_label="profile_seed",
                metadata={"field": "persona_name", "value": persona_name},
            ),
        )
    if persona_summary:
        rows.append(
            SpeakerMemoryRow(
                memory_type="self_fact",
                content=persona_summary,
                speaker=agent_slug,
                source_label="profile_seed",
                metadata={"field": "persona_summary", "value": persona_summary},
            ),
        )
    if speaking_style:
        rows.append(
            SpeakerMemoryRow(
                memory_type="self_style",
                content=speaking_style,
                speaker=agent_slug,
                source_label="profile_seed",
                metadata={"field": "speaking_style", "value": speaking_style},
            ),
        )
    namespace = agent_memories_ns(user.id, agent_slug)
    with speaker_profile_store(store) as active_store:
        for row in rows:
            put_memory(active_store, namespace, row)
    return profile


def seed_relationship_memories(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> RelationshipProfile:
    profile = RelationshipProfile(
        agent_slug=agent_slug,
        rapport_level="new",
        last_interaction_summary="First time talking with this user.",
    )
    if not langmem_enabled():
        return profile
    rows = [
        SpeakerMemoryRow(
            memory_type="rapport",
            content="The relationship with this user is new.",
            speaker=agent_slug,
            source_label="profile_seed",
            metadata={"field": "rapport_level", "value": "new"},
        ),
        SpeakerMemoryRow(
            memory_type="shared_event",
            content="First time talking with this user.",
            speaker=agent_slug,
            source_label="profile_seed",
            metadata={"field": "last_interaction_summary", "value": profile.last_interaction_summary},
        ),
    ]
    namespace = relationship_memories_ns(user.id, agent_slug)
    with speaker_profile_store(store) as active_store:
        for row in rows:
            put_memory(active_store, namespace, row)
    return profile


def format_memories_for_prompt(
    user: Any,
    agent_slug: str,
    *,
    store: BaseStore | None = None,
) -> str:
    if not langmem_enabled():
        return ""
    sections: list[str] = []
    with speaker_profile_store(store) as active_store:
        user_rows = list_memories(active_store, user_memories_ns(user.id))
        if user_rows:
            lines = [f"- [{row.memory_type}] {row.content}" for row in user_rows[:12]]
            sections.append("User memories:\n" + "\n".join(lines))
        agent_rows = list_memories(active_store, agent_memories_ns(user.id, agent_slug))
        if agent_rows:
            lines = [f"- [{row.memory_type}] {row.content}" for row in agent_rows[:8]]
            sections.append("Your remembered persona:\n" + "\n".join(lines))
        rel_rows = list_memories(active_store, relationship_memories_ns(user.id, agent_slug))
        if rel_rows:
            lines = [f"- [{row.memory_type}] {row.content}" for row in rel_rows[:8]]
            sections.append("Your relationship with this user:\n" + "\n".join(lines))
    return "\n\n".join(sections)


@dataclass(frozen=True)
class LangMemAdminEntry:
    store_key: str
    namespace: tuple[str, ...]
    namespace_path: str
    user_id: int | None
    namespace_kind: str
    agent_slug: str | None
    memory_type: str
    content: str
    confidence: float
    speaker: str
    source_label: str
    metadata: dict[str, Any]

    @property
    def entry_id(self) -> str:
        raw = f"{self.namespace_path}::{self.store_key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_namespace_metadata(namespace: tuple[str, ...]) -> dict[str, Any]:
    if len(namespace) < 3 or namespace[0] != "users":
        return {"user_id": None, "namespace_kind": "unknown", "agent_slug": None}
    user_raw = str(namespace[1])
    user_id = int(user_raw) if user_raw.isdigit() else None
    if len(namespace) == 3 and namespace[2] == "memories":
        return {"user_id": user_id, "namespace_kind": "user", "agent_slug": None}
    if len(namespace) == 5 and namespace[2] == "agents":
        agent_slug = str(namespace[3])
        tail = str(namespace[4])
        if tail == "memories":
            kind = "agent"
        elif tail == "relationship":
            kind = "relationship"
        else:
            kind = "unknown"
        return {"user_id": user_id, "namespace_kind": kind, "agent_slug": agent_slug}
    return {"user_id": user_id, "namespace_kind": "unknown", "agent_slug": None}


def _iter_store_items(
    store: BaseStore,
    namespace: tuple[str, ...],
    *,
    limit: int,
) -> Iterator[Any]:
    try:
        results = store.search(namespace, limit=limit)
    except Exception:
        logger.debug("LangMem admin search failed for %s", namespace, exc_info=True)
        return
    yield from results


def iter_all_langmem_entries(
    store: BaseStore,
    *,
    limit_per_namespace: int = 200,
) -> Iterator[LangMemAdminEntry]:
    try:
        namespaces = store.list_namespaces(prefix=("users",), limit=500)
    except Exception:
        logger.debug("LangMem admin list_namespaces failed", exc_info=True)
        namespaces = []
    for namespace in namespaces:
        ns_meta = parse_namespace_metadata(namespace)
        namespace_path = "/".join(namespace)
        for item in _iter_store_items(store, namespace, limit=limit_per_namespace):
            row = _item_to_row(item)
            if row is None or not _row_is_allowed(row):
                continue
            normalized = normalize_memory_row(
                row,
                namespace_kind=str(ns_meta["namespace_kind"]),
                agent_slug=ns_meta["agent_slug"],
            )
            if normalized is None:
                continue
            store_key = str(getattr(item, "key", "") or memory_row_key(row))
            yield LangMemAdminEntry(
                store_key=store_key,
                namespace=namespace,
                namespace_path=namespace_path,
                user_id=ns_meta["user_id"],
                namespace_kind=str(ns_meta["namespace_kind"]),
                agent_slug=ns_meta["agent_slug"],
                memory_type=normalized.memory_type,
                content=normalized.content,
                confidence=normalized.confidence,
                speaker=normalized.speaker,
                source_label=normalized.source_label,
                metadata=normalized.metadata if isinstance(normalized.metadata, dict) else {},
            )


def _matches_filters(
    entry: LangMemAdminEntry,
    *,
    user_id: str | None,
    memory_type: str | None,
    namespace_kind: str | None,
    agent_slug: str | None,
    query: str | None,
) -> bool:
    if user_id:
        if entry.user_id is None or str(entry.user_id) != str(user_id).strip():
            return False
    if memory_type and entry.memory_type != memory_type.strip():
        return False
    if namespace_kind:
        normalized_kind = namespace_kind.strip()
        if normalized_kind == "learner":
            normalized_kind = "user"
        if entry.namespace_kind != normalized_kind:
            return False
    if agent_slug and (entry.agent_slug or "").strip() != agent_slug.strip():
        return False
    if query:
        q = query.strip().casefold()
        haystack = " ".join(
            [
                entry.content,
                entry.memory_type,
                entry.source_label,
                entry.speaker,
                entry.namespace_path,
                json.dumps(entry.metadata, default=str),
            ],
        ).casefold()
        if q not in haystack and not any(term in haystack for term in _tokenize(q)):
            return False
    return True


def list_langmem_entries_for_admin(
    *,
    user_id: str | None = None,
    memory_type: str | None = None,
    namespace_kind: str | None = None,
    agent_slug: str | None = None,
    query: str | None = None,
    store: BaseStore | None = None,
) -> list[LangMemAdminEntry]:
    if not langmem_enabled():
        return []
    entries: list[LangMemAdminEntry] = []
    with speaker_profile_store(store) as active_store:
        for entry in iter_all_langmem_entries(active_store):
            if _matches_filters(
                entry,
                user_id=user_id,
                memory_type=memory_type,
                namespace_kind=namespace_kind,
                agent_slug=agent_slug,
                query=query,
            ):
                entries.append(entry)
    entries.sort(
        key=lambda item: (
            item.user_id if item.user_id is not None else 0,
            item.namespace_kind,
            item.agent_slug or "",
            item.memory_type,
            item.store_key,
        ),
    )
    return entries


def get_langmem_entry_for_admin(
    entry_id: str,
    *,
    store: BaseStore | None = None,
) -> LangMemAdminEntry | None:
    for entry in list_langmem_entries_for_admin(store=store):
        if entry.entry_id == entry_id:
            return entry
    return None
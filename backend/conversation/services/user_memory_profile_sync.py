from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from backend.conversation.models import UserMemory
from backend.conversation.services.user_memory_extraction import (
    normalize_memory_content,
)


@dataclass(frozen=True)
class ProfileSyncResult:
    created_count: int = 0
    skipped_count: int = 0
    created_ids: tuple[int, ...] = field(default_factory=tuple)


def _profile_memory_specs(user: Any) -> list[tuple[str, str]]:
    profile = getattr(user, "userprofile", None)
    if profile is None:
        return []

    specs: list[tuple[str, str]] = []
    preferred_name = (profile.preferred_name or "").strip()
    major = (profile.major or "").strip()
    cefr_level = (profile.cefr_level or "").strip().upper()
    if preferred_name:
        specs.append(("preferred_name", f"The user prefers to be called {preferred_name}."))
    if major:
        specs.append(("major", f"The user's major is {major}."))
    if cefr_level:
        specs.append(("cefr_level", f"The user's current CEFR level is {cefr_level}."))
    return specs


def _profile_duplicate_exists(user: Any, content: str) -> bool:
    normalized = normalize_memory_content(content)
    memories = UserMemory.objects.filter(
        user=user,
        is_active=True,
        memory_type="profile",
    ).only("content")
    for memory in memories:
        if normalize_memory_content(memory.content) == normalized:
            return True
    return False


def sync_user_profile_memory(user: Any) -> ProfileSyncResult:
    created_ids: list[int] = []
    skipped_count = 0
    for field_name, content in _profile_memory_specs(user):
        if _profile_duplicate_exists(user, content):
            skipped_count += 1
            continue
        memory = UserMemory.objects.create(
            user=user,
            memory_type="profile",
            content=content,
            source_label="profile_sync",
            source_uri=f"userprofile:{user.id}:{field_name}",
            confidence=1.0,
            metadata={"kind": "profile_sync", "field": field_name, "user_id": user.id},
        )
        created_ids.append(memory.id)
    return ProfileSyncResult(
        created_count=len(created_ids),
        skipped_count=skipped_count,
        created_ids=tuple(created_ids),
    )

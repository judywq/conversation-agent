from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from backend.conversation.models import TurnRecord
from backend.conversation.services.user_memory_extraction import (
    schedule_memory_extraction_for_turn,
)
from backend.conversation.services.user_memory_profile_sync import (
    sync_user_profile_memory,
)
from backend.users.models import UserProfile


@receiver(post_save, sender=TurnRecord)
def trigger_user_memory_after_user_turn(
    sender,
    instance: TurnRecord,
    created,
    raw,
    **kwargs,
) -> None:
    if raw or not created or instance.speaker_type != TurnRecord.SPEAKER_TYPE_USER:
        return
    sync_user_profile_memory(instance.session.user)
    schedule_memory_extraction_for_turn(instance)


@receiver(post_save, sender=UserProfile)
def trigger_profile_memory_sync(
    sender,
    instance: UserProfile,
    raw,
    update_fields,
    **kwargs,
) -> None:
    if raw:
        return
    profile_fields = {"preferred_name", "major", "cefr_level"}
    if update_fields is not None and not profile_fields & set(update_fields):
        return
    sync_user_profile_memory(instance.user)

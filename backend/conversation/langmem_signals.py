from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from backend.conversation.models import TurnRecord
from backend.conversation.services.langmem_extraction import schedule_langmem_extraction_for_turn
from backend.conversation.services.speaker_profiles import seed_user_profile_from_userprofile
from backend.users.models import UserProfile


@receiver(post_save, sender=TurnRecord)
def trigger_langmem_after_turn(
    sender,
    instance: TurnRecord,
    created,
    raw,
    **kwargs,
) -> None:
    if raw or not created:
        return
    schedule_langmem_extraction_for_turn(instance)


@receiver(post_save, sender=UserProfile)
def trigger_langmem_profile_seed(
    sender,
    instance: UserProfile,
    raw,
    update_fields,
    **kwargs,
) -> None:
    if raw:
        return
    profile_fields = {"preferred_name", "major", "cefr_level", "ocean"}
    if update_fields is not None and not profile_fields & set(update_fields):
        return
    seed_user_profile_from_userprofile(instance.user)
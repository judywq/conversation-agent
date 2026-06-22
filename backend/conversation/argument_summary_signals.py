from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from backend.conversation.models import TurnRecord
from backend.conversation.services.argument_summary import schedule_argument_summary_refresh_for_session_id


@receiver(post_save, sender=TurnRecord)
def trigger_argument_summary_refresh(
    sender,
    instance: TurnRecord,
    created,
    raw,
    **kwargs,
) -> None:
    if raw or not created:
        return
    if instance.speaker_type == TurnRecord.SPEAKER_TYPE_MAKESHIFT:
        return
    schedule_argument_summary_refresh_for_session_id(instance.session_id)

import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from backend.conversation.services.profile_audio import generate_cefr_topic_samples
from backend.users.models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task()
def generate_cefr_samples_for_user(user_id: int, topic: str, generation: int) -> dict:
    """Generate CEFR listening samples in the background and persist them on the profile."""
    topic_log = topic[:200]
    logger.info(
        "cefr_samples_task_start user_id=%s topic=%s generation=%s",
        user_id,
        topic_log,
        generation,
    )
    try:
        user = User.objects.select_related("userprofile").get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("cefr_samples_task_skipped missing_user user_id=%s", user_id)
        return {"ok": False, "reason": "missing_user"}

    if not hasattr(user, "userprofile"):
        logger.warning("cefr_samples_task_skipped missing_profile user_id=%s", user_id)
        return {"ok": False, "reason": "missing_profile"}

    try:
        samples = generate_cefr_topic_samples(topic=topic, user=user)
    except Exception:
        logger.exception(
            "cefr_samples_task_failed user_id=%s topic=%s generation=%s",
            user_id,
            topic_log,
            generation,
        )
        updated = UserProfile.objects.filter(
            user_id=user_id,
            cefr_samples_generation=generation,
        ).update(cefr_samples_status=UserProfile.CefrSamplesStatus.FAILED)
        return {"ok": False, "reason": "pipeline_failed", "status_updated": bool(updated)}

    profile = UserProfile.objects.get(user_id=user_id)
    if profile.cefr_samples_generation != generation:
        logger.info(
            "cefr_samples_task_stale user_id=%s topic=%s generation=%s current_generation=%s",
            user_id,
            topic_log,
            generation,
            profile.cefr_samples_generation,
        )
        return {"ok": False, "reason": "stale"}

    profile.cefr_sample_topic = topic
    profile.cefr_sample_choices = samples
    profile.cefr_samples_status = UserProfile.CefrSamplesStatus.READY
    profile.save(
        update_fields=["cefr_sample_topic", "cefr_sample_choices", "cefr_samples_status"],
    )
    logger.info(
        "cefr_samples_task_complete user_id=%s topic=%s generation=%s sample_count=%d",
        user_id,
        topic_log,
        generation,
        len(samples),
    )
    return {"ok": True, "sample_count": len(samples)}

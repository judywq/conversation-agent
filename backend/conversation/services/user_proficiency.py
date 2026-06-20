from __future__ import annotations

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.cefr_levels import normalize_user_cefr_level

PROFILE_ONBOARDING_CEFR_TOPIC = "University life and learning English"


def longest_user_utterance_for_session(session: ConversationSession) -> str:
    utterances = (
        TurnRecord.objects.filter(
            session=session,
            speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        )
        .order_by("turn_index", "id")
        .values_list("utterance", flat=True)
    )
    cleaned = [str(text or "").strip() for text in utterances if str(text or "").strip()]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


def build_agent_proficiency_guidance(
    *,
    cefr_level: str | None,
    reference_utterance: str | None,
) -> str:
    reference = str(reference_utterance or "").strip()
    if reference:
        return (
            "Proficiency sample (shows the user's English level only; do not copy its topic or wording): "
            f'"{reference}"'
        )
    level = normalize_user_cefr_level(cefr_level)
    return f"Default proficiency: CEFR level {level}."


def resolve_user_proficiency(*, user) -> dict[str, str]:
    """Load the latest proficiency fields from the database for prompt injection."""
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    fresh_user = user_model.objects.select_related("userprofile").get(pk=user.pk)
    profile = getattr(fresh_user, "userprofile", None)
    cefr_level = (getattr(profile, "cefr_level", "") or "").strip()
    reference_utterance = (getattr(profile, "proficiency_reference_utterance", "") or "").strip()
    guidance = build_agent_proficiency_guidance(
        cefr_level=cefr_level,
        reference_utterance=reference_utterance,
    )
    return {
        "cefr_level": normalize_user_cefr_level(cefr_level) if cefr_level else "",
        "reference_utterance": reference_utterance,
        "proficiency_guidance": guidance,
    }


def update_proficiency_from_session(session: ConversationSession) -> bool:
    utterance = longest_user_utterance_for_session(session)
    if not utterance:
        return False
    profile = getattr(session.user, "userprofile", None)
    if profile is None:
        return False
    profile.proficiency_reference_utterance = utterance
    profile.save(update_fields=["proficiency_reference_utterance"])
    return True

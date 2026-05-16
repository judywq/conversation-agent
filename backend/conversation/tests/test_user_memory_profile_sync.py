import pytest

from backend.conversation.models import UserMemory
from backend.conversation.services.user_memory_profile_sync import (
    sync_user_profile_memory,
)
from backend.users.api.serializers import CustomUserDetailsSerializer

EXPECTED_PROFILE_MEMORY_COUNT = 3


@pytest.mark.django_db
def test_sync_user_profile_memory_creates_stable_profile_memories(user):
    user.userprofile.preferred_name = "Judy"
    user.userprofile.major = "Computer Science"
    user.userprofile.cefr_level = "B2"
    user.userprofile.cefr_sample_topic = "learning Chinese"
    user.userprofile.cefr_sample_choices = [{"level": "B2", "text": "Generated sample"}]

    result = sync_user_profile_memory(user)

    assert result.created_count == EXPECTED_PROFILE_MEMORY_COUNT
    contents = list(
        UserMemory.objects.filter(user=user).values_list("content", flat=True),
    )
    assert "用户希望被称呼为 Judy。" in contents
    assert "用户专业是 Computer Science。" in contents
    assert "用户当前 CEFR 水平是 B2。" in contents
    assert all("Generated sample" not in content for content in contents)
    assert all("learning Chinese" not in content for content in contents)


@pytest.mark.django_db
def test_sync_user_profile_memory_skips_duplicates(user):
    user.userprofile.preferred_name = "Judy"
    user.userprofile.save()

    sync_user_profile_memory(user)
    result = sync_user_profile_memory(user)

    assert result.created_count == 0
    assert result.skipped_count == 1
    assert UserMemory.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_sync_user_profile_memory_runs_when_extraction_flag_disabled(settings, user):
    settings.USER_MEMORY_EXTRACTION_ENABLED = False
    user.userprofile.major = "Computer Science"

    result = sync_user_profile_memory(user)

    assert result.created_count == 1


@pytest.mark.django_db
def test_profile_update_signal_triggers_profile_memory_sync(user):
    serializer = CustomUserDetailsSerializer(
        instance=user,
        data={"major": "Computer Science"},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors

    serializer.save()

    assert UserMemory.objects.filter(
        user=user,
        source_label="profile_sync",
        content="用户专业是 Computer Science。",
    ).exists()

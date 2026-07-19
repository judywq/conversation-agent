from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from backend.users.models import UserProfile

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="cefruser", email="cefr@example.com", password="x")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_post_cefr_samples_enqueues_and_completes(api_client, user):
    samples = [
        {"level": level, "text": f"{level} text", "audio_url": f"https://example.com/{level}.mp3"}
        for level in ("A1", "A2", "B1", "B2", "C1", "C2")
    ]
    with patch(
        "backend.conversation.tasks.generate_cefr_topic_samples",
        return_value=samples,
    ):
        res = api_client.post("/api/conversation/cefr-samples/", {"topic": "Computer Science"}, format="json")

    assert res.status_code == 202
    assert res.data["status"] == "pending"
    assert res.data["samples"] == []

    user.userprofile.refresh_from_db()
    assert user.userprofile.cefr_samples_status == UserProfile.CefrSamplesStatus.READY
    assert user.userprofile.cefr_sample_topic == "Computer Science"
    assert len(user.userprofile.cefr_sample_choices) == 6


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_stale_generation_is_ignored(api_client, user):
    profile = user.userprofile
    profile.cefr_samples_generation = 1
    profile.cefr_samples_status = UserProfile.CefrSamplesStatus.PENDING
    profile.cefr_sample_topic = "Biology"
    profile.save()

    from backend.conversation.tasks import generate_cefr_samples_for_user

    with patch(
        "backend.conversation.tasks.generate_cefr_topic_samples",
        return_value=[{"level": "A1", "text": "old", "audio_url": "https://x/a.mp3"}],
    ):
        result = generate_cefr_samples_for_user(user.id, "Biology", generation=0)

    assert result["reason"] == "stale"
    profile.refresh_from_db()
    assert profile.cefr_samples_status == UserProfile.CefrSamplesStatus.PENDING
    assert profile.cefr_sample_choices == []


def test_get_cefr_samples_status(api_client, user):
    profile = user.userprofile
    profile.cefr_samples_status = UserProfile.CefrSamplesStatus.READY
    profile.cefr_sample_topic = "Math"
    profile.cefr_sample_choices = [{"level": "B1", "text": "hi", "audio_url": None}]
    profile.save()

    res = api_client.get("/api/conversation/cefr-samples/")
    assert res.status_code == 200
    assert res.data["status"] == "ready"
    assert res.data["topic"] == "Math"
    assert len(res.data["samples"]) == 1

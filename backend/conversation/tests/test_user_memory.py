from django.contrib import admin
from django.core.exceptions import ValidationError

import pytest

from backend.conversation.admin import UserMemoryAdmin
from backend.conversation.models import UserMemory


@pytest.mark.django_db
def test_user_memory_defaults(user):
    memory = UserMemory.objects.create(
        user=user,
        content="The user prefers concise corrections.",
    )

    assert memory.user == user
    assert memory.memory_type == "profile"
    assert memory.confidence == 1.0
    assert memory.is_active is True
    assert memory.metadata == {}
    assert memory.embedding is None
    assert memory.embedding_model == ""
    assert memory.embedding_dimensions is None
    assert memory.embedding_text_hash == ""
    assert memory.embedding_updated_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_user_memory_rejects_out_of_range_confidence(user, confidence):
    memory = UserMemory(
        user=user,
        content="The user is preparing for IELTS speaking.",
        confidence=confidence,
    )

    with pytest.raises(ValidationError):
        memory.full_clean()


@pytest.mark.django_db
def test_user_memory_accepts_source_fields_and_metadata(user):
    memory = UserMemory.objects.create(
        user=user,
        content="The user wants B2-level follow-up questions.",
        memory_type="learning_preference",
        source_label="manual admin note",
        source_uri="admin://user-memory/manual",
        confidence=0.75,
        metadata={"topic": "speaking"},
    )

    assert memory.memory_type == "learning_preference"
    assert memory.source_label == "manual admin note"
    assert memory.source_uri == "admin://user-memory/manual"
    assert memory.confidence == 0.75
    assert memory.metadata == {"topic": "speaking"}


@pytest.mark.django_db
def test_user_memory_admin_searches_content_and_source(rf, user):
    UserMemory.objects.create(
        user=user,
        content="The user prefers short corrective feedback.",
        source_label="manual note",
        source_uri="admin://memory/1",
        memory_type="learning_preference",
    )
    model_admin = UserMemoryAdmin(UserMemory, admin.site)
    request = rf.get("/admin/conversation/usermemory/", {"q": "corrective"})
    request.user = user

    queryset, _may_have_duplicates = model_admin.get_search_results(
        request,
        UserMemory.objects.all(),
        "corrective",
    )

    assert queryset.count() == 1


@pytest.mark.django_db
def test_user_memory_admin_bulk_activity_actions(rf, user):
    disabled = UserMemory.objects.create(
        user=user,
        content="Disabled memory",
        is_active=False,
    )
    enabled = UserMemory.objects.create(
        user=user,
        content="Enabled memory",
        is_active=True,
    )
    model_admin = UserMemoryAdmin(UserMemory, admin.site)
    request = rf.post("/admin/conversation/usermemory/")
    request.user = user
    model_admin.message_user = lambda *args, **kwargs: None

    model_admin.enable_selected_memories(
        request,
        UserMemory.objects.filter(pk=disabled.pk),
    )
    disabled.refresh_from_db()
    assert disabled.is_active is True

    model_admin.disable_selected_memories(
        request,
        UserMemory.objects.filter(pk=enabled.pk),
    )
    enabled.refresh_from_db()
    assert enabled.is_active is False

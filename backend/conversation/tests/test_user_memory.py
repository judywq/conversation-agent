import pytest
from django.core.exceptions import ValidationError

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

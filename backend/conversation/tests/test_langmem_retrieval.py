import pytest
from contextlib import contextmanager
from langgraph.store.memory import InMemoryStore

from backend.conversation.models import ConversationSession
from backend.conversation.models import UserMemory
from backend.conversation.services.retrieval import retrieve
from backend.conversation.services.speaker_memories import put_memory
from backend.conversation.services.speaker_profile_schemas import SpeakerMemoryRow
from backend.conversation.services.speaker_profile_schemas import learner_memories_ns


@contextmanager
def _memory_store_cm(store):
    yield store


@pytest.mark.django_db
def test_retrieve_memory_langmem_first(user, monkeypatch, settings):
    settings.EMBEDDING_PROVIDER = "fake"
    memory_store = InMemoryStore()
    session = ConversationSession.objects.create(user=user, topic="class discussion")

    put_memory(
        memory_store,
        learner_memories_ns(user.id),
        SpeakerMemoryRow(
            memory_type="learning_goal",
            content="The user wants to practice debate skills.",
            speaker="user",
            source_label="test",
        ),
    )
    UserMemory.objects.create(
        user=user,
        memory_type="learning_goal",
        content="The user wants to practice debate skills.",
        source_label="legacy",
        confidence=1.0,
    )

    monkeypatch.setattr(
        "backend.conversation.services.speaker_memories.speaker_profile_store",
        lambda store=None: _memory_store_cm(store or memory_store),
    )

    context = retrieve(
        "debate skills",
        session=session,
        user=user,
        sources={"memory"},
        top_k=3,
    )

    assert context.items
    assert context.items[0].metadata.get("langmem") is True

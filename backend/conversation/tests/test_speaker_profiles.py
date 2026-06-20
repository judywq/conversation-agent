import pytest
from langgraph.store.memory import InMemoryStore

from backend.conversation.services.speaker_memories import list_memories
from backend.conversation.services.speaker_memories import put_memory
from backend.conversation.services.speaker_memories import search_user_memories
from backend.conversation.services.speaker_profile_schemas import SpeakerMemoryRow
from backend.conversation.services.speaker_profile_schemas import agent_memories_ns
from backend.conversation.services.speaker_profile_schemas import agent_self_ns
from backend.conversation.services.speaker_profile_schemas import user_memories_ns
from backend.conversation.services.speaker_profile_schemas import relationship_memories_ns
from backend.conversation.services.speaker_profile_schemas import relationship_ns
from backend.conversation.services.speaker_profile_schemas import user_profile_ns
from backend.conversation.services.speaker_profiles import dump_all_profiles
from backend.conversation.services.speaker_profiles import format_profiles_for_prompt
from backend.conversation.services.speaker_profiles import get_agent_profile
from backend.conversation.services.speaker_profiles import get_relationship_profile
from backend.conversation.services.speaker_profiles import get_user_profile
from backend.conversation.services.speaker_profiles import seed_agent_profile
from backend.conversation.services.speaker_profiles import seed_relationship_profile
from backend.conversation.services.speaker_profiles import seed_user_profile_from_userprofile


@pytest.fixture
def memory_store():
    return InMemoryStore()


def test_namespace_helpers():
    from backend.conversation.services.speaker_profile_schemas import learner_memories_ns

    assert user_profile_ns(42) == ("users", "42", "memories")
    assert user_memories_ns(42) == ("users", "42", "memories")
    assert learner_memories_ns(42) == user_memories_ns(42)
    assert agent_self_ns(42, "fact_checker") == (
        "users",
        "42",
        "agents",
        "fact_checker",
        "memories",
    )
    assert agent_memories_ns(42, "fact_checker") == agent_self_ns(42, "fact_checker")
    assert relationship_ns(7, "idea_explorer") == relationship_memories_ns(7, "idea_explorer")


@pytest.mark.django_db
def test_seed_user_profile_from_userprofile(user, memory_store):
    user.userprofile.preferred_name = "Judy"
    user.userprofile.major = "Computer Science"
    user.userprofile.cefr_level = "b1"
    user.userprofile.ocean = {"openness": "high"}
    user.userprofile.save()

    profile = seed_user_profile_from_userprofile(user, store=memory_store)

    assert profile.preferred_name == "Judy"
    assert profile.major == "Computer Science"
    assert profile.cefr_level == "B1"
    loaded = get_user_profile(user, store=memory_store)
    assert loaded is not None
    assert loaded.preferred_name == "Judy"
    rows = list_memories(memory_store, user_memories_ns(user.id))
    assert len(rows) >= 3


@pytest.mark.django_db
def test_seed_agent_and_relationship_profiles(user, memory_store):
    seed_agent_profile(
        user,
        "discussion_driver",
        display_name="Liam",
        persona_name="Discussion Driver",
        persona_summary="Energetic discussion leader.",
        store=memory_store,
    )
    seed_relationship_profile(user, "discussion_driver", store=memory_store)

    agent = get_agent_profile(user, "discussion_driver", store=memory_store)
    relationship = get_relationship_profile(user, "discussion_driver", store=memory_store)

    assert agent is not None
    assert agent.display_name == "Liam"
    assert relationship is not None
    assert relationship.rapport_level == "new"


@pytest.mark.django_db
def test_format_profiles_for_prompt(user, memory_store):
    seed_user_profile_from_userprofile(user, store=memory_store)
    seed_agent_profile(
        user,
        "fact_checker",
        display_name="Sophia",
        persona_name="Fact Checker",
        store=memory_store,
    )
    seed_relationship_profile(user, "fact_checker", store=memory_store)

    bundle = format_profiles_for_prompt(user, "fact_checker", store=memory_store)
    rendered = bundle.format_for_prompt()

    assert "User profile:" in rendered
    assert "Your relationship with this user:" in rendered
    assert "Sophia" in rendered


@pytest.mark.django_db
def test_dump_all_profiles(user, memory_store):
    seed_user_profile_from_userprofile(user, store=memory_store)
    payload = dump_all_profiles(user, store=memory_store)

    assert payload["enabled"] is True
    assert payload["user_id"] == user.id
    assert "memories" in payload
    assert any("memories" in key for key in payload["memories"])


@pytest.mark.django_db
def test_search_user_memories(user, memory_store):
    put_memory(
        memory_store,
        user_memories_ns(user.id),
        SpeakerMemoryRow(
            memory_type="learning_goal",
            content="The user wants to improve academic writing.",
            speaker="user",
        ),
    )
    hits = search_user_memories(user, "academic writing", store=memory_store, top_k=3)
    assert hits
    assert hits[0][0].memory_type == "learning_goal"


@pytest.mark.django_db
def test_speaker_profiles_disabled(settings, user, memory_store):
    settings.SPEAKER_PROFILES_ENABLED = False
    user.userprofile.preferred_name = "Judy"
    user.userprofile.save()

    seed_user_profile_from_userprofile(user, store=memory_store)

    assert get_user_profile(user, store=memory_store) is None


def test_parse_namespace_metadata():
    from backend.conversation.services.speaker_memories import parse_namespace_metadata

    assert parse_namespace_metadata(("users", "42", "memories")) == {
        "user_id": 42,
        "namespace_kind": "user",
        "agent_slug": None,
    }
    assert parse_namespace_metadata(("users", "7", "agents", "fact_checker", "memories")) == {
        "user_id": 7,
        "namespace_kind": "agent",
        "agent_slug": "fact_checker",
    }


def test_expected_speaker_for_namespaces():
    from backend.conversation.services.speaker_memories import expected_speaker
    from backend.conversation.services.speaker_memories import is_valid_speaker
    from backend.conversation.services.speaker_memories import normalize_memory_row

    assert expected_speaker(namespace_kind="user", agent_slug=None, memory_type="preference") == "user"
    assert expected_speaker(
        namespace_kind="agent",
        agent_slug="idea_explorer",
        memory_type="self_fact",
    ) == "idea_explorer"

    user_row = SpeakerMemoryRow(
        memory_type="self_fact",
        content="I go jogging twice a week.",
        speaker="user",
    )
    assert normalize_memory_row(user_row, namespace_kind="agent", agent_slug="idea_explorer") is None
    with pytest.raises(ValueError, match="Invalid speaker"):
        put_memory(
            InMemoryStore(),
            agent_memories_ns(1, "idea_explorer"),
            user_row,
        )

    agent_row = SpeakerMemoryRow(
        memory_type="self_fact",
        content="I teach statistics on weekends.",
        speaker="idea_explorer",
    )
    normalized = normalize_memory_row(agent_row, namespace_kind="agent", agent_slug="idea_explorer")
    assert normalized is not None
    assert normalized.speaker == "idea_explorer"
    assert is_valid_speaker(agent_row, namespace_kind="agent", agent_slug="idea_explorer") is True


@pytest.mark.django_db
def test_sanitize_removes_user_facts_duplicated_in_agent_namespace(user, memory_store):
    from backend.conversation.services.speaker_memories import sanitize_namespace_memories

    put_memory(
        memory_store,
        user_memories_ns(user.id),
        SpeakerMemoryRow(
            memory_type="lifestyle",
            content="I go jogging and do light gym workouts about two to three times per week.",
            speaker="user",
        ),
    )
    memory_store.put(
        agent_memories_ns(user.id, "fact_checker"),
        "misattributed-jogging",
        {
            "kind": "SpeakerMemoryRow",
            "content": {
                "memory_type": "self_fact",
                "content": "I go jogging and do light gym workouts about two to three times per week.",
                "speaker": "fact_checker",
            },
        },
    )
    deleted, _updated = sanitize_namespace_memories(
        memory_store,
        agent_memories_ns(user.id, "fact_checker"),
    )
    assert deleted == 1
    assert not list_memories(memory_store, agent_memories_ns(user.id, "fact_checker"))


def test_put_memory_uses_langmem_wrapped_format(memory_store):
    from backend.conversation.services.speaker_memories import wrap_row_for_store
    from backend.conversation.services.speaker_profile_schemas import LANGMEM_ROW_KIND

    row = SpeakerMemoryRow(
        memory_type="identity",
        content="The user enjoys hiking.",
        speaker="user",
    )
    put_memory(memory_store, user_memories_ns(1), row)
    items = list(memory_store.search(user_memories_ns(1), limit=5))
    assert items
    value = items[0].value
    assert value["kind"] == LANGMEM_ROW_KIND
    assert value["content"]["memory_type"] == "identity"
    assert wrap_row_for_store(row)["content"]["content"] == "The user enjoys hiking."


@pytest.mark.django_db
def test_sanitize_deletes_opinions(user, memory_store):
    from backend.conversation.services.speaker_memories import list_memories
    from backend.conversation.services.speaker_memories import sanitize_namespace_memories

    with pytest.raises(ValueError, match="Blocked"):
        put_memory(
            memory_store,
            user_memories_ns(user.id),
            SpeakerMemoryRow(
                memory_type="opinion",
                content="The user believes taxes are too high.",
                speaker="user",
            ),
        )
    memory_store.put(
        user_memories_ns(user.id),
        "legacy-opinion",
        {
            "kind": "SpeakerMemoryRow",
            "content": {
                "memory_type": "opinion",
                "content": "Legacy opinion row.",
                "speaker": "user",
            },
        },
    )
    put_memory(
        memory_store,
        user_memories_ns(user.id),
        SpeakerMemoryRow(memory_type="preference", content="The user enjoys swimming.", speaker="user"),
    )
    deleted, updated = sanitize_namespace_memories(memory_store, user_memories_ns(user.id))
    assert deleted == 1
    rows = list_memories(memory_store, user_memories_ns(user.id))
    assert len(rows) == 1
    assert rows[0].memory_type == "preference"


@pytest.mark.django_db
def test_list_langmem_entries_for_admin(user, memory_store):
    from backend.conversation.services.speaker_memories import list_langmem_entries_for_admin

    put_memory(
        memory_store,
        user_memories_ns(user.id),
        SpeakerMemoryRow(
            memory_type="identity",
            content="The user prefers to be called Judy.",
            speaker="user",
        ),
    )
    entries = list_langmem_entries_for_admin(user_id=str(user.id), store=memory_store)
    assert len(entries) == 1
    assert entries[0].memory_type == "identity"
    assert entries[0].namespace_kind == "user"
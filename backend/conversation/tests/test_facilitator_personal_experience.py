import pytest
from langgraph.store.memory import InMemoryStore

from backend.conversation.services.agent import resolve_agent_retrieval_sources
from backend.conversation.services.facilitator import coerce_speech_act_plan
from backend.conversation.services.facilitator import is_personal_experience_plan
from backend.conversation.services.speaker_memories import agent_profile_from_rows
from backend.conversation.services.speaker_memories import put_memory
from backend.conversation.services.speaker_profile_schemas import SpeakerMemoryRow
from backend.conversation.services.speaker_profile_schemas import agent_memories_ns
from backend.conversation.services.speaker_profiles import build_agent_personal_profile_context
from backend.conversation.services.speaker_profiles import seed_agent_profile


def test_is_personal_experience_plan_true_when_flag_set():
    assert is_personal_experience_plan({"personal_experience": True, "content_requirement": ""})


def test_is_personal_experience_plan_true_from_content_requirement_keywords():
    assert is_personal_experience_plan(
        {
            "personal_experience": False,
            "content_requirement": "Share a brief personal dorm story related to this.",
        },
    )


def test_is_personal_experience_plan_false_for_generic_instruction():
    assert not is_personal_experience_plan(
        {
            "personal_experience": False,
            "content_requirement": "Add a factual point about the topic.",
        },
    )


def test_coerce_speech_act_plan_sets_memory_when_personal_experience_true():
    plan = coerce_speech_act_plan(
        {
            "speech_act": {"type": "ASSERTIVES", "subtype": "opinion"},
            "content_requirement": "Share a brief personal dorm story related to this.",
            "personal_experience": True,
            "retrieval need": "none",
        },
    )
    assert plan["personal_experience"] is True
    assert plan["retrieval_requirement"] == "memory"


def test_coerce_speech_act_plan_infers_personal_experience_from_content():
    plan = coerce_speech_act_plan(
        {
            "speech_act": {"type": "ASSERTIVES", "subtype": "opinion"},
            "content_requirement": "Give a first-person example from your classes.",
        },
    )
    assert plan["personal_experience"] is True
    assert plan["retrieval_requirement"] == "memory"


def test_resolve_agent_retrieval_sources_includes_memory_for_personal_experience():
    sources = resolve_agent_retrieval_sources(
        {
            "type": "ASSERTIVES",
            "subtype": "opinion",
            "personal_experience": True,
            "retrieval_requirement": "none",
        },
    )
    assert "memory" in sources
    assert "exemplar" in sources


def test_agent_profile_from_rows_includes_self_event_and_preference():
    profile = agent_profile_from_rows(
        "agent_1",
        [
            SpeakerMemoryRow(
                memory_type="self_event",
                content="I lived in a dorm my first year.",
                speaker="agent_1",
            ),
            SpeakerMemoryRow(
                memory_type="self_preference",
                content="I prefer studying in the library.",
                speaker="agent_1",
            ),
        ],
    )
    assert "I lived in a dorm my first year." in profile.self_revealed_facts
    assert "I prefer studying in the library." in profile.self_revealed_facts


@pytest.mark.django_db
def test_build_agent_personal_profile_context_returns_seeded_facts(user, memory_store, settings):
    settings.SPEAKER_PROFILES_ENABLED = True
    settings.LANGMEM_ENABLED = True
    seed_agent_profile(
        user,
        "discussion_driver",
        display_name="Liam",
        persona_name="Discussion Driver",
        persona_summary="Energetic discussion leader.",
        store=memory_store,
    )
    namespace = agent_memories_ns(user.id, "discussion_driver")
    put_memory(
        memory_store,
        namespace,
        SpeakerMemoryRow(
            memory_type="self_event",
            content="I joined the debate club freshman year.",
            speaker="discussion_driver",
            source_label="test",
        ),
    )

    context = build_agent_personal_profile_context(
        user,
        "discussion_driver",
        topic="campus clubs",
        store=memory_store,
    )

    assert "Reuse these personal details" in context
    assert "debate club" in context


@pytest.mark.django_db
def test_build_agent_personal_profile_context_empty_when_no_profile(user, memory_store, settings):
    settings.SPEAKER_PROFILES_ENABLED = True
    settings.LANGMEM_ENABLED = True
    context = build_agent_personal_profile_context(
        user,
        "agent_1",
        topic="dorms",
        store=memory_store,
    )
    assert "No personal anecdotes on file" in context

import random

import pytest

from backend.conversation.consumers import ConversationConsumer
from backend.conversation.prompts import load_agent_persona_prompts
from backend.conversation.services.agent_characters import AgentCharacterError
from backend.conversation.services.agent_characters import apply_persona_overrides
from backend.conversation.services.agent_characters import assign_random_personas
from backend.conversation.services.agent_characters import get_agent_characters
from backend.conversation.services.agent_characters import load_agent_characters
from backend.conversation.services.agent_characters import resolve_character_ids

ALL_PERSONAS = {
    "Supportive Builder",
    "Fact Checker",
    "Discussion Driver",
    "Idea Explorer",
    "Tense Skeptic",
}

CURRENT_ROSTER_IDS = {"hiyori", "shizuku", "chitose", "hibiki"}


def test_default_roster_loads_unique_characters_and_personas():
    characters = load_agent_characters()
    assert len(characters) == 4
    assert {c.id for c in characters} == CURRENT_ROSTER_IDS
    assert len({c.persona_name for c in characters}) == 4
    assert {c.persona_name for c in characters}.issubset(ALL_PERSONAS)


def test_persona_prompt_catalog_has_five_roles():
    assert {p.persona_name for p in load_agent_persona_prompts()} == ALL_PERSONAS


def test_assign_random_personas_unique_from_pool_preserves_voice():
    base = list(get_agent_characters())
    assigned = assign_random_personas(base, rng=random.Random(42))
    assert [c.id for c in assigned] == [c.id for c in base]
    assert [c.voice_preset_name for c in assigned] == [c.voice_preset_name for c in base]
    personas = [c.persona_name for c in assigned]
    assert len(personas) == len(set(personas))
    assert set(personas).issubset(ALL_PERSONAS)


def test_apply_persona_overrides_sets_personas_and_keeps_voice():
    base = resolve_character_ids(["hiyori", "shizuku"])
    updated = apply_persona_overrides(
        base,
        {"hiyori": "Fact Checker", "shizuku": "Tense Skeptic"},
    )
    assert [c.persona_name for c in updated] == ["Fact Checker", "Tense Skeptic"]
    assert [c.voice_preset_name for c in updated] == [c.voice_preset_name for c in base]


def test_apply_persona_overrides_rejects_unknown_persona():
    base = resolve_character_ids(["hiyori"])
    with pytest.raises(AgentCharacterError, match="Unknown persona_name"):
        apply_persona_overrides(base, {"hiyori": "Not A Persona"})


def test_apply_persona_overrides_rejects_duplicates():
    base = resolve_character_ids(["hiyori", "shizuku"])
    with pytest.raises(AgentCharacterError, match="Duplicate persona_name"):
        apply_persona_overrides(
            base,
            {"hiyori": "Fact Checker", "shizuku": "Fact Checker"},
        )


def test_apply_persona_overrides_rejects_missing():
    base = resolve_character_ids(["hiyori", "shizuku"])
    with pytest.raises(AgentCharacterError, match="Missing persona"):
        apply_persona_overrides(base, {"hiyori": "Fact Checker"})


def test_resolve_character_ids_rejects_unknown():
    with pytest.raises(AgentCharacterError, match="Unknown character id"):
        resolve_character_ids(["hiyori", "not-a-character"])


def test_resolve_character_ids_rejects_duplicates():
    with pytest.raises(AgentCharacterError, match="unique"):
        resolve_character_ids(["hiyori", "hiyori"])


def test_resolve_character_ids_rejects_too_many():
    ids = [c.id for c in get_agent_characters()[:4]]
    with pytest.raises(AgentCharacterError, match="at most"):
        resolve_character_ids(ids)


def test_resolve_character_ids_preserves_order():
    resolved = resolve_character_ids(["hibiki", "hiyori", "chitose"])
    assert [c.id for c in resolved] == ["hibiki", "hiyori", "chitose"]


@pytest.mark.django_db
def test_create_session_from_character_ids_with_persona_overrides(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = consumer._create_session_sync(
        topic="Climate policy",
        character_ids=["shizuku", "hibiki"],
        character_personas={
            "shizuku": "Fact Checker",
            "hibiki": "Discussion Driver",
        },
    )

    agents = list(session.agent_profiles.order_by("agent_id"))
    assert session.agent_count == 2
    assert [a.agent_id for a in agents] == ["hibiki", "shizuku"]
    shizuku = next(a for a in agents if a.agent_id == "shizuku")
    assert shizuku.display_name == "Shizuku"
    assert shizuku.personality["persona_name"] == "Fact Checker"
    assert shizuku.personality["live2d_url"] == "/live2d/shizuku/shizuku.model3.json"
    assert shizuku.personality["character_id"] == "shizuku"
    assert shizuku.personality["voice_gender"] == "female"
    hibiki = next(a for a in agents if a.agent_id == "hibiki")
    assert hibiki.personality["persona_name"] == "Discussion Driver"
    assert hibiki.personality["voice_gender"] == "female"


@pytest.mark.django_db
def test_create_session_without_personas_assigns_unique_random(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = consumer._create_session_sync(
        topic="Climate policy",
        character_ids=["hiyori", "chitose"],
    )
    agents = list(session.agent_profiles.all())
    personas = [a.personality["persona_name"] for a in agents]
    assert len(personas) == len(set(personas))
    assert set(personas).issubset(ALL_PERSONAS)


@pytest.mark.django_db
def test_participants_payload_includes_live2d_url(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = consumer._create_session_sync(
        topic="Climate policy",
        character_ids=["hiyori"],
        character_personas={"hiyori": "Idea Explorer"},
    )
    participants = consumer._participants_payload_sync(session.id)
    agents = [p for p in participants if p["type"] == "agent"]
    assert len(agents) == 1
    assert agents[0]["id"] == "hiyori"
    assert agents[0]["live2d_url"] == "/live2d/hiyori/Hiyori.model3.json"
    assert agents[0]["character_id"] == "hiyori"
    assert agents[0]["persona_name"] == "Idea Explorer"


@pytest.mark.django_db
def test_create_session_rejects_invalid_character_ids(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    with pytest.raises(AgentCharacterError):
        consumer._create_session_sync(
            topic="Climate policy",
            character_ids=["nope"],
        )


@pytest.mark.django_db
def test_characters_api_returns_unique_randomized_personas(user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/conversation/characters/")
    assert response.status_code == 200
    characters = response.json()["characters"]
    assert len(characters) == 4
    personas = [c["persona_name"] for c in characters]
    assert len(personas) == len(set(personas))
    assert set(personas).issubset(ALL_PERSONAS)
    for character, base in zip(characters, get_agent_characters()):
        assert character["id"] == base.id
        assert character["voice_preset_name"] == base.voice_preset_name

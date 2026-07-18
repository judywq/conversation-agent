import pytest

from backend.conversation.consumers import ConversationConsumer
from backend.conversation.services.agent_characters import AgentCharacterError
from backend.conversation.services.agent_characters import get_agent_characters
from backend.conversation.services.agent_characters import load_agent_characters
from backend.conversation.services.agent_characters import resolve_character_ids


def test_default_roster_loads_five_unique_personas():
    characters = load_agent_characters()
    assert len(characters) == 5
    assert len({c.id for c in characters}) == 5
    assert len({c.persona_name for c in characters}) == 5
    assert {c.persona_name for c in characters} == {
        "Supportive Builder",
        "Fact Checker",
        "Discussion Driver",
        "Idea Explorer",
        "Tense Skeptic",
    }


def test_resolve_character_ids_rejects_unknown():
    with pytest.raises(AgentCharacterError, match="Unknown character id"):
        resolve_character_ids(["haru", "not-a-character"])


def test_resolve_character_ids_rejects_duplicates():
    with pytest.raises(AgentCharacterError, match="unique"):
        resolve_character_ids(["haru", "haru"])


def test_resolve_character_ids_rejects_too_many():
    ids = [c.id for c in get_agent_characters()[:4]]
    with pytest.raises(AgentCharacterError, match="at most"):
        resolve_character_ids(ids)


def test_resolve_character_ids_preserves_order():
    resolved = resolve_character_ids(["mao", "haru", "natori"])
    assert [c.id for c in resolved] == ["mao", "haru", "natori"]


@pytest.mark.django_db
def test_create_session_from_character_ids(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = consumer._create_session_sync(
        topic="Climate policy",
        character_ids=["haru", "natori"],
    )

    agents = list(session.agent_profiles.order_by("agent_id"))
    assert session.agent_count == 2
    assert [a.agent_id for a in agents] == ["haru", "natori"]
    haru = next(a for a in agents if a.agent_id == "haru")
    assert haru.display_name == "Haru"
    assert haru.personality["persona_name"] == "Supportive Builder"
    assert haru.personality["live2d_url"] == "/live2d/haru/Haru.model3.json"
    assert haru.personality["character_id"] == "haru"
    assert haru.personality["voice_gender"] == "female"
    natori = next(a for a in agents if a.agent_id == "natori")
    assert natori.personality["persona_name"] == "Fact Checker"
    assert natori.personality["voice_gender"] == "male"


@pytest.mark.django_db
def test_participants_payload_includes_live2d_url(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = consumer._create_session_sync(
        topic="Climate policy",
        character_ids=["hiyori"],
    )
    participants = consumer._participants_payload_sync(session.id)
    agents = [p for p in participants if p["type"] == "agent"]
    assert len(agents) == 1
    assert agents[0]["id"] == "hiyori"
    assert agents[0]["live2d_url"] == "/live2d/hiyori/Hiyori.model3.json"
    assert agents[0]["character_id"] == "hiyori"
    assert agents[0]["persona_name"] == "Discussion Driver"


@pytest.mark.django_db
def test_create_session_rejects_invalid_character_ids(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    with pytest.raises(AgentCharacterError):
        consumer._create_session_sync(
            topic="Climate policy",
            character_ids=["nope"],
        )

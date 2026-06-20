from asgiref.sync import async_to_sync
import pytest

from backend.conversation.consumers import MAX_AGENT_COUNT
from backend.conversation.consumers import MAX_MALE_AGENTS
from backend.conversation.consumers import ConversationConsumer
from backend.conversation.services.names import pick_voice_preset_for_persona


@pytest.mark.django_db
def test_create_session_clamps_agent_count_to_max(user):
    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = async_to_sync(consumer._create_session)(topic="Climate policy", agent_count=5)

    assert session.agent_count == MAX_AGENT_COUNT
    assert session.agent_profiles.count() == MAX_AGENT_COUNT


@pytest.mark.django_db
def test_create_session_caps_male_agents_at_one(user, monkeypatch):
    real_pick = pick_voice_preset_for_persona

    def always_male_unless_forced(persona_name, *, gender=None, rng=None):
        return real_pick(persona_name, gender=gender or "male")

    monkeypatch.setattr(
        "backend.conversation.consumers.pick_voice_preset_for_persona",
        always_male_unless_forced,
    )

    consumer = ConversationConsumer()
    consumer.scope = {"user": user}

    session = async_to_sync(consumer._create_session)(topic="Climate policy", agent_count=3)
    agents = list(session.agent_profiles.all())
    male_count = sum(
        1 for agent in agents if (agent.personality or {}).get("voice_gender") == "male"
    )

    assert len(agents) == 3
    assert male_count == MAX_MALE_AGENTS

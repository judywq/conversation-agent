import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.conversation.models import AgentProfile
from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.services.facilitator import build_facilitator_plan
from backend.conversation.services.facilitator import build_speech_act_distribution_for_prompt
from backend.conversation.services.makeshift import invite_user
from backend.conversation.services.turn_processor import TurnMetadata
from backend.conversation.services.turn_processor import append_turn
@pytest.mark.django_db
def test_append_turn_increments_major_and_assertives_subtype(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    md = TurnMetadata(
        type="ASSERTIVES",
        subtype="inform",
        target=None,
        content_requirement="",
        retrieval_requirement="",
    )
    append_turn(
        session,
        speaker="agent_1",
        speaker_type=TurnRecord.SPEAKER_TYPE_AGENT,
        utterance="fact",
        metadata=md,
    )
    session.refresh_from_db()
    assert session.speech_act_counters["major"]["ASSERTIVES"] == 1
    assert session.speech_act_counters["subtype"]["ASSERTIVES"]["inform"] == 1


@pytest.mark.django_db
def test_makeshift_increments_counters_without_bumping_turn_count(user):
    session = ConversationSession.objects.create(user=user, topic="t", turn_count=1)
    AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "A"})
    append_turn(
        session,
        speaker="user",
        speaker_type=TurnRecord.SPEAKER_TYPE_USER,
        utterance="hello",
        metadata=TurnMetadata(
            type="ASSERTIVES",
            subtype="opinion",
            target=None,
            content_requirement="",
            retrieval_requirement="",
        ),
    )
    session.refresh_from_db()
    assert session.turn_count == 2

    invite_user(session)
    session.refresh_from_db()
    assert session.turn_count == 2
    assert session.speech_act_counters["major"]["DIRECTIVES"] == 1
    assert session.speech_act_counters["subtype"]["DIRECTIVES"]["invite"] == 1


@pytest.mark.django_db
def test_build_speech_act_distribution_for_prompt_structure(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    session.speech_act_counters = {
        "major": {"ASSERTIVES": 9, "DIRECTIVES": 1},
        "subtype": {
            "ASSERTIVES": {"inform": 8, "opinion": 1},
            "DIRECTIVES": {"request_info": 1},
        },
    }
    session.save(update_fields=["speech_act_counters"])

    ctx = build_speech_act_distribution_for_prompt(session)
    assert "0.74" in ctx["sa_target_weights_major"]
    summary = json.loads(ctx["sa_session_summary"])
    assert summary["total_classified_turns"] == 10
    assert summary["major_empirical_rates"]["ASSERTIVES"] == pytest.approx(0.9)
    assert "steering_hint" in summary


@pytest.mark.django_db
def test_build_facilitator_plan_includes_distribution_context(user):
    session = ConversationSession.objects.create(user=user, topic="topic")
    agent = AgentProfile.objects.create(session=session, agent_id="agent_1", personality={"persona_name": "A"})

    plan_json = json.dumps(
        {
            "type": "ASSERTIVES",
            "subtype": "inform",
            "target": "everyone",
            "content_requirement": "Say something.",
            "retrieval need": "none",
        },
    )

    captured: list[str] = []

    def capture_invoke(messages):
        captured.append(messages[0].content)
        return SimpleNamespace(content=plan_json)

    mock_llm = SimpleNamespace(invoke=capture_invoke)

    with patch(
        "backend.conversation.services.facilitator.get_default_chat_llm",
        return_value=mock_llm,
    ):
        build_facilitator_plan(session, agent=agent)

    assert captured
    text = captured[0]
    assert "Corpus target weights (major SA types" in text
    assert '"ASSERTIVES": 0.74' in text
    assert "steering_hint" in text
    assert "{sa_session_summary}" not in text

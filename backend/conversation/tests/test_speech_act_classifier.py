import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.conversation.models import ConversationSession
from backend.conversation.services.turn_processor import classify_user_speech_act
from backend.conversation.services.turn_processor import process_user_turn


@pytest.mark.django_db
def test_append_user_turn_classified_uses_llm_speech_act_metadata(user):
    session = ConversationSession.objects.create(user=user, topic="ethics in AI")

    plan_json = json.dumps(
        {
            "type": "EXPRESSIVES",
            "subtype": "agree",
            "target": "agent_1",
            "content_requirement": "",
            "retrieval_requirement": "",
        },
    )
    mock_llm = SimpleNamespace(
        invoke=lambda _messages: SimpleNamespace(content=plan_json),
    )

    with patch(
        "backend.conversation.services.turn_processor.get_default_chat_llm",
        return_value=mock_llm,
    ):
        processed = process_user_turn(
            session,
            "I fully agree with that point.",
            source="text",
            audio_url=None,
        )

    turn = processed.turn
    assert turn.speech_act == "EXPRESSIVES"
    assert turn.subtype == "agree"
    assert turn.target == "agent_1"
    assert turn.utterance == "I fully agree with that point."
    assert turn.source == "text"
    assert turn.audio_url is None


@pytest.mark.django_db
def test_classify_user_speech_act_falls_back_on_invalid_json(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    mock_llm = SimpleNamespace(
        invoke=lambda _messages: SimpleNamespace(content="not valid json {"),
    )

    with patch(
        "backend.conversation.services.turn_processor.get_default_chat_llm",
        return_value=mock_llm,
    ):
        plan = classify_user_speech_act(session, "hello", source="text", audio_url=None)

    assert plan.get("type") == "ASSERTIVES"
    assert plan.get("subtype") == "opinion"


@pytest.mark.django_db
def test_classify_user_speech_act_picks_matching_sentence_from_array(user):
    session = ConversationSession.objects.create(user=user, topic="t")
    utterance = "Could you search the information online?"
    plan_json = json.dumps(
        [
            {
                "file_name": "sample.txt",
                "sentence": "Different sentence.",
                "context": {"previous_sentence": None, "next_sentence": None},
                "SA_type": "ASSERTIVES",
                "subtype": "opinion",
            },
            {
                "file_name": "sample.txt",
                "sentence": utterance,
                "context": {"previous_sentence": None, "next_sentence": None},
                "SA_type": "DIRECTIVES",
                "subtype": "request_action",
            },
        ],
    )
    mock_llm = SimpleNamespace(
        invoke=lambda _messages: SimpleNamespace(content=plan_json),
    )

    with patch(
        "backend.conversation.services.turn_processor.get_default_chat_llm",
        return_value=mock_llm,
    ):
        plan = classify_user_speech_act(session, utterance, source="text", audio_url=None)

    assert plan.get("type") == "DIRECTIVES"
    assert plan.get("subtype") == "request_action"

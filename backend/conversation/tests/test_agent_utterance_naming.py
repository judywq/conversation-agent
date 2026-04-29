import pytest

from backend.conversation.services.agent import _enforce_directive_target_name
from backend.conversation.services.agent import _avoid_question_ending_when_not_request
from backend.conversation.services.agent import _limit_to_three_sentences
from backend.conversation.services.agent import _strip_bracketed_text


def test_enforce_directive_target_name_prepends_when_missing():
    out = _enforce_directive_target_name(
        "Could you explain your idea a bit more?",
        speech_act_type="DIRECTIVES",
        target_display_name="Alex",
    )
    assert out.endswith(", Alex?")


def test_enforce_directive_target_name_noop_when_present_case_insensitive():
    out = _enforce_directive_target_name(
        "alex, could you explain your idea a bit more?",
        speech_act_type="DIRECTIVES",
        target_display_name="Alex",
    )
    assert out == "alex, could you explain your idea a bit more?"


def test_enforce_directive_target_name_noop_for_non_directives():
    out = _enforce_directive_target_name(
        "I agree with that.",
        speech_act_type="EXPRESSIVES",
        target_display_name="Alex",
    )
    assert out == "I agree with that."


def test_strip_bracketed_text_removes_parentheses_and_brackets():
    out = _strip_bracketed_text("I agree (as agent_2) [meta]. Let's continue.")
    assert "agent_2" not in out
    assert "meta" not in out


def test_avoid_question_ending_converts_non_directives_to_period():
    out = _avoid_question_ending_when_not_request(
        "I agree with that?",
        speech_act_type="ASSERTIVES",
        speech_act_subtype="opinion",
    )
    assert out == "I agree with that."


def test_avoid_question_ending_keeps_request_like_directives():
    out = _avoid_question_ending_when_not_request(
        "What do you think?",
        speech_act_type="DIRECTIVES",
        speech_act_subtype="request_info",
    )
    assert out == "What do you think?"


def test_limit_to_three_sentences_truncates():
    out = _limit_to_three_sentences("One. Two! Three? Four. Five.")
    assert out == "One. Two! Three?"


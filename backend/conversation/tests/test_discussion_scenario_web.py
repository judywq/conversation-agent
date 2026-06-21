import json

import pytest

from backend.conversation.services.cefr_levels import normalize_user_cefr_level
from backend.conversation.services.discussion_scenario import setup_discussion_context
from backend.conversation.services.discussion_scenario import build_discussion_scenario_proficiency_guidance
from backend.conversation.services.discussion_scenario import generate_scenario_with_llm


def test_normalize_user_cefr_level_defaults_to_b1():
    assert normalize_user_cefr_level("") == "B1"
    assert normalize_user_cefr_level(None) == "B1"
    assert normalize_user_cefr_level("invalid") == "B1"


def test_normalize_user_cefr_level_preserves_valid_level():
    assert normalize_user_cefr_level("b2") == "B2"


@pytest.mark.django_db
def test_generate_scenario_with_llm_subtopic_mode_includes_cefr(monkeypatch):
    captured = {}

    class FakeLLM:
        def invoke(self, messages):
            captured["prompt"] = messages[0].content
            return type(
                "Result",
                (),
                {"content": json.dumps({"scenario": "Should schools use AI tutors?"})},
            )()

    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario.get_default_chat_llm",
        lambda: FakeLLM(),
    )

    result = generate_scenario_with_llm(
        category="technology-ai",
        subtopic="ai-teachers",
        articles=[],
        cefr_level="A2",
    )

    assert "User proficiency: A2" in captured["prompt"]
    assert "beginner learners" in captured["prompt"]
    assert "No news articles are available" in captured["prompt"]
    assert result.knowledge_source == "none"
    assert result.scenario.endswith("?")


@pytest.mark.django_db
def test_generate_scenario_with_llm_uses_reference_utterance_when_present(monkeypatch):
    captured = {}

    class FakeLLM:
        def invoke(self, messages):
            captured["prompt"] = messages[0].content
            return type(
                "Result",
                (),
                {"content": json.dumps({"scenario": "Should schools use AI tutors?"})},
            )()

    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario.get_default_chat_llm",
        lambda: FakeLLM(),
    )

    utterance = "I think AI tutors could help students who need extra practice."
    result = generate_scenario_with_llm(
        category="technology-ai",
        subtopic="ai-teachers",
        articles=[],
        cefr_level="C1",
        reference_utterance=utterance,
    )

    assert "User proficiency sample" in captured["prompt"]
    assert utterance in captured["prompt"]
    assert "User proficiency: C1" not in captured["prompt"]
    assert result.scenario.endswith("?")


def test_build_discussion_scenario_proficiency_guidance_prefers_reference():
    guidance = build_discussion_scenario_proficiency_guidance(
        cefr_level="B1",
        reference_utterance="I think the policy is quite complicated.",
    )
    assert "User proficiency sample" in guidance
    assert "complicated" in guidance
    assert "User proficiency: B1" not in guidance


def test_build_discussion_scenario_proficiency_guidance_uses_cefr_without_reference():
    guidance = build_discussion_scenario_proficiency_guidance(
        cefr_level="A2",
        reference_utterance="",
    )
    assert guidance.startswith("User proficiency: A2")
    assert "beginner learners" in guidance


@pytest.mark.django_db
def test_setup_discussion_context_web_fallback(monkeypatch):
    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario.ensure_articles_for_taxonomy",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario.generate_scenario_with_llm",
        lambda **kwargs: type(
            "Result",
            (),
            {
                "scenario": "Your university plans to ban smartphones in class. Do you agree?",
                "category": kwargs["category"],
                "subtopic": kwargs["subtopic"],
                "category_name": "Technology & AI",
                "subtopic_name": "AI teachers",
                "article_id": None,
                "article_title": "",
                "article_ids": [],
                "articles": [],
                "knowledge_source": "none",
            },
        )(),
    )
    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario._fetch_web_context_for_scenario",
        lambda **kwargs: ("Summary: Recent debate about AI tutors.\n1. Title: Example", True),
    )

    result = setup_discussion_context(
        category="technology-ai",
        subtopic="ai-teachers",
        cefr_level="B1",
    )

    assert result.knowledge_source == "web"
    assert result.web_context_fetched is True
    assert "AI tutors" in result.web_context
    assert result.article_ids == []

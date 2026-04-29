import pytest

from backend.conversation.consumers import select_agent_personas_for_session
from backend.conversation.prompts import load_prompts_catalog
from backend.conversation.prompts import render_prompt_template


def test_prompts_catalog_loads_expected_sections():
    catalog = load_prompts_catalog()
    assert len(catalog.agent_prompts) == 5
    assert "You are the Facilitator" in catalog.facilitator_template
    assert "You are a Speech Act Classifier." in catalog.speech_act_classifier_template


def test_render_prompt_template_preserves_non_placeholder_braces():
    template = 'Example JSON: {"type":"x"} topic={topic}'
    rendered = render_prompt_template(template, topic="ai ethics")
    assert '{"type":"x"}' in rendered
    assert "topic=ai ethics" in rendered


def test_select_agent_personas_for_session_returns_three_unique():
    selected = select_agent_personas_for_session({}, count=3)
    assert len(selected) == 3
    names = [p.prompt.persona_name for p in selected]
    assert len(set(names)) == 3


def test_select_agent_personas_for_session_raises_if_count_too_large():
    with pytest.raises(ValueError):
        select_agent_personas_for_session({}, count=10)

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


def test_agent_persona_template_substitutes_major():
    catalog = load_prompts_catalog()
    template = catalog.agent_prompts[0].template
    assert "{major}" in template

    rendered = render_prompt_template(
        template,
        agent_name="agent_1",
        agent_display_name="Alex",
        proficiency_level="B2",
        proficiency_guidance="Default proficiency: CEFR level B2.",
        major="Computer Science",
        topic="climate",
        history="[]",
        target="everyone",
        target_type="everyone",
        target_display_name="",
        speech_act_type="ASSERTIVES",
        speech_act_subtype="inform",
        content_requirement="",
        retrieved_context="",
        argument_summary_bullets="- Dorms build community",
        audio_tags="[reflective]",
    )
    assert "Computer Science" in rendered
    assert "Discussion points already covered" in rendered
    assert "Dorms build community" in rendered
    assert "{major}" not in rendered

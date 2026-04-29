from backend.conversation.services.agent_selection import select_complementary_agent_personas


def test_select_complementary_agent_personas_prefers_low_traits():
    selected = select_complementary_agent_personas(
        {
            "openness": "low",
            "conscientiousness": "low",
            "extraversion": "high",
            "agreeableness": "medium",
            "neuroticism": "high",
        },
        count=3,
    )

    names = [item.prompt.persona_name for item in selected]
    assert "Idea Explorer" in names
    assert "Fact Checker" in names
    assert "Supportive Builder" in names
    assert "Tense Skeptic" not in names

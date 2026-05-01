from __future__ import annotations

from dataclasses import dataclass

from backend.conversation.prompts import AgentPersonaPrompt
from backend.conversation.prompts import load_agent_persona_prompts

OCEAN_ARCHETYPE_MAP = {
    "openness": "Idea Explorer",
    "conscientiousness": "Fact Checker",
    "extraversion": "Discussion Driver",
    "agreeableness": "Supportive Builder",
    "neuroticism": "Tense Skeptic",
}

LEVEL_SCORE = {"low": 2, "medium": 1, "high": 0}
NEUROTICISM_SCORE = {"low": 2, "medium": 1, "high": 0}

PERSONA_PRIORITY = {
    "Idea Explorer": 0,
    "Supportive Builder": 1,
    "Discussion Driver": 2,
    "Tense Skeptic": 3,
    "Fact Checker": 4,
}


@dataclass(frozen=True)
class SelectedPersona:
    prompt: AgentPersonaPrompt
    source_trait: str
    user_level: str
    complementary_score: int


def select_complementary_agent_personas(ocean: dict[str, str], *, count: int = 3) -> list[SelectedPersona]:
    prompts_by_name = {p.persona_name: p for p in load_agent_persona_prompts()}
    selections: list[SelectedPersona] = []
    for trait, persona_name in OCEAN_ARCHETYPE_MAP.items():
        prompt = prompts_by_name.get(persona_name)
        if prompt is None:
            continue
        user_level = str(ocean.get(trait) or "medium").lower()
        score_map = NEUROTICISM_SCORE if trait == "neuroticism" else LEVEL_SCORE
        score = score_map.get(user_level, 1)
        selections.append(
            SelectedPersona(
                prompt=prompt,
                source_trait=trait,
                user_level=user_level,
                complementary_score=score,
            ),
        )

    ranked = sorted(
        selections,
        key=lambda item: (
            -item.complementary_score,
            PERSONA_PRIORITY.get(item.prompt.persona_name, 999),
            item.prompt.persona_name,
        ),
    )
    positive = [item for item in ranked if item.complementary_score >= 0]
    chosen = positive[:count]
    if len(chosen) < count:
        chosen = ranked[:count]
    return chosen

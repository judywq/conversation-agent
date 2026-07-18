from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.conversation.prompts import load_agent_persona_prompts
from backend.conversation.services.names import voice_preset_by_name

# Keep in sync with ConversationConsumer.MAX_AGENT_COUNT (avoid circular import).
MAX_SELECTABLE_CHARACTERS = 3

_DEFAULT_CHARACTERS_PATH = Path(__file__).resolve().parent.parent / "data" / "agent_characters.json"

REQUIRED_FIELDS = (
    "id",
    "display_name",
    "live2d_url",
    "persona_name",
    "gender",
    "voice_preset_name",
)


@dataclass(frozen=True)
class AgentCharacter:
    id: str
    display_name: str
    live2d_url: str
    persona_name: str
    gender: str
    voice_preset_name: str

    def to_dict(self) -> dict:
        return asdict(self)


class AgentCharacterError(ValueError):
    """Invalid roster config or character_ids selection."""


def default_characters_path() -> Path:
    return _DEFAULT_CHARACTERS_PATH


def load_agent_characters(path: Path | None = None) -> list[AgentCharacter]:
    p = path or default_characters_path()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise AgentCharacterError("agent_characters.json must be a JSON array")
    characters = [_parse_character(item, index=i) for i, item in enumerate(raw)]
    _validate_roster(characters)
    return characters


@lru_cache(maxsize=1)
def get_agent_characters() -> tuple[AgentCharacter, ...]:
    return tuple(load_agent_characters())


def agent_characters_by_id(path: Path | None = None) -> dict[str, AgentCharacter]:
    characters = load_agent_characters(path) if path is not None else list(get_agent_characters())
    return {c.id: c for c in characters}


def resolve_character_ids(
    character_ids: list[str],
    *,
    path: Path | None = None,
) -> list[AgentCharacter]:
    if not character_ids:
        raise AgentCharacterError("character_ids must not be empty")
    if len(character_ids) > MAX_SELECTABLE_CHARACTERS:
        raise AgentCharacterError(f"Select at most {MAX_SELECTABLE_CHARACTERS} partners")
    if len(set(character_ids)) != len(character_ids):
        raise AgentCharacterError("character_ids must be unique")

    by_id = agent_characters_by_id(path)
    resolved: list[AgentCharacter] = []
    for cid in character_ids:
        key = str(cid or "").strip()
        character = by_id.get(key)
        if character is None:
            raise AgentCharacterError(f"Unknown character id: {cid}")
        resolved.append(character)
    return resolved


def _parse_character(item: object, *, index: int) -> AgentCharacter:
    if not isinstance(item, dict):
        raise AgentCharacterError(f"Character entry {index} must be an object")
    missing = [f for f in REQUIRED_FIELDS if not str(item.get(f) or "").strip()]
    if missing:
        raise AgentCharacterError(f"Character entry {index} missing fields: {', '.join(missing)}")
    return AgentCharacter(
        id=str(item["id"]).strip(),
        display_name=str(item["display_name"]).strip(),
        live2d_url=str(item["live2d_url"]).strip(),
        persona_name=str(item["persona_name"]).strip(),
        gender=str(item["gender"]).strip().lower(),
        voice_preset_name=str(item["voice_preset_name"]).strip(),
    )


def _validate_roster(characters: list[AgentCharacter]) -> None:
    if not characters:
        raise AgentCharacterError("agent_characters.json must contain at least one character")

    ids = [c.id for c in characters]
    if len(set(ids)) != len(ids):
        raise AgentCharacterError("Duplicate character id in agent_characters.json")

    persona_names = {p.persona_name for p in load_agent_persona_prompts()}
    seen_personas: set[str] = set()
    for character in characters:
        if character.persona_name not in persona_names:
            raise AgentCharacterError(
                f"Unknown persona_name for {character.id}: {character.persona_name}",
            )
        if character.persona_name in seen_personas:
            raise AgentCharacterError(
                f"Duplicate persona_name in roster: {character.persona_name}",
            )
        seen_personas.add(character.persona_name)
        if character.gender not in {"male", "female"}:
            raise AgentCharacterError(
                f"Invalid gender for {character.id}: {character.gender}",
            )
        if voice_preset_by_name(character.voice_preset_name) is None:
            raise AgentCharacterError(
                f"Unknown voice_preset_name for {character.id}: {character.voice_preset_name}",
            )

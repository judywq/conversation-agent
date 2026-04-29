from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent / "data" / "prompts"


@dataclass(frozen=True)
class AgentPersonaPrompt:
    persona_name: str
    template: str


@dataclass(frozen=True)
class PromptCatalog:
    agent_prompts: list[AgentPersonaPrompt]
    facilitator_template: str
    speech_act_classifier_template: str


def default_prompts_path() -> Path:
    return _DEFAULT_PROMPTS_DIR


def load_prompts_catalog(path: Path | None = None) -> PromptCatalog:
    p = path or _DEFAULT_PROMPTS_DIR
    if not p.is_dir():
        msg = f"Prompt source must be a directory: {p}"
        raise ValueError(msg)
    return _load_prompts_from_directory(p)


@lru_cache(maxsize=1)
def get_prompts_catalog() -> PromptCatalog:
    return load_prompts_catalog()


def load_agent_persona_prompts() -> list[AgentPersonaPrompt]:
    return get_prompts_catalog().agent_prompts


def load_facilitator_prompt() -> str:
    return get_prompts_catalog().facilitator_template


def load_speech_act_classifier_prompt() -> str:
    return get_prompts_catalog().speech_act_classifier_template


def load_additional_prompt(name: str) -> str:
    path = _DEFAULT_PROMPTS_DIR / name
    if not path.exists():
        msg = f"Prompt file not found: {path}"
        raise ValueError(msg)
    return path.read_text(encoding="utf-8").strip()


def render_prompt_template(template: str, **values: object) -> str:
    """
    Render only known {placeholder} tokens.
    Leaves unrelated curly braces untouched (e.g. JSON examples in prompts).
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def _load_prompts_from_directory(prompts_dir: Path) -> PromptCatalog:
    shared_path = prompts_dir / "agent_shared.txt"
    facilitator_path = prompts_dir / "facilitator.txt"
    classifier_path = prompts_dir / "speech_act_classifier.txt"

    if not shared_path.exists() or not facilitator_path.exists() or not classifier_path.exists():
        msg = (
            "Missing split prompt files in "
            f"{prompts_dir}. Required: agent_shared.txt, facilitator.txt, speech_act_classifier.txt"
        )
        raise ValueError(msg)

    shared_template = shared_path.read_text(encoding="utf-8").strip()
    facilitator_template = facilitator_path.read_text(encoding="utf-8").strip()
    speech_act_classifier_template = classifier_path.read_text(encoding="utf-8").strip()

    persona_files = sorted(prompts_dir.glob("agent_*.txt"))
    persona_files = [p for p in persona_files if p.name != "agent_shared.txt"]
    agent_prompts: list[AgentPersonaPrompt] = []
    for persona_path in persona_files:
        persona_raw = persona_path.read_text(encoding="utf-8").strip()
        if not persona_raw:
            continue
        persona_name, persona_section = _extract_persona_file_parts(persona_raw, persona_path)
        agent_prompts.append(
            AgentPersonaPrompt(
                persona_name=persona_name,
                template=render_prompt_template(
                    shared_template,
                    persona_name=persona_name,
                    persona_section=persona_section,
                ),
            ),
        )

    if not agent_prompts:
        msg = f"No agent persona files found in {prompts_dir}"
        raise ValueError(msg)

    return PromptCatalog(
        agent_prompts=agent_prompts,
        facilitator_template=facilitator_template,
        speech_act_classifier_template=speech_act_classifier_template,
    )


def _extract_persona_file_parts(text: str, path: Path) -> tuple[str, str]:
    m = re.search(r"^PersonaName:\s*(.+)$", text, re.MULTILINE)
    if not m:
        msg = f"Missing 'PersonaName:' line in {path}"
        raise ValueError(msg)
    persona_name = m.group(1).strip()
    persona_section = re.sub(r"^PersonaName:\s*.+$", "", text, count=1, flags=re.MULTILINE).strip()
    return persona_name, persona_section



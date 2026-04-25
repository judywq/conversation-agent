from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROMPT_KEY_AGENT_UTTERANCE = "agent_utterance"
PROMPT_KEY_FACILITATOR_PLAN = "facilitator_plan"

_DEFAULT_PROMPTS_PATH = Path(__file__).resolve().parent / "data" / "conversation_llm_prompts.txt"


@dataclass(frozen=True)
class PromptPair:
    """System and user text for a conversation LLM call."""

    key: str
    system_template: str
    user_template: str

    @property
    def user_is_json_payload(self) -> bool:
        return not (self.user_template and self.user_template.strip())


def default_prompts_path() -> Path:
    return _DEFAULT_PROMPTS_PATH


def load_prompt_blocks_from_file(path: Path | None = None) -> dict[str, PromptPair]:
    """Parse conversation_llm_prompts.txt into prompt keys and templates."""
    p = path or _DEFAULT_PROMPTS_PATH
    text = p.read_text(encoding="utf-8")
    return _parse_blocks(text)


def _parse_blocks(text: str) -> dict[str, PromptPair]:
    out: dict[str, PromptPair] = {}
    for m in re.finditer(
        r"^---\s*([a-zA-Z0-9_]+)\s*---\s*\n(.*?)(?=^---\s*[a-zA-Z0-9_]+\s*---\s*$|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    ):
        name, body = m.group(1), m.group(2)
        system_t, user_t = _split_system_user(body)
        out[name] = PromptPair(
            key=name,
            system_template=system_t,
            user_template=user_t,
        )
    return out


def _split_system_user(block: str) -> tuple[str, str]:
    m_sys = re.search(r"\[SYSTEM\]\s*(.*?)(?=\[USER\]|$)", block, re.DOTALL)
    m_user = re.search(r"\[USER\]\s*(.*)$", block, re.DOTALL)
    system = m_sys.group(1).strip() if m_sys else ""
    user = m_user.group(1).strip() if m_user else ""
    return system, user


def get_prompt_pair(key: str) -> PromptPair:
    """
    Return prompts for key from the database, or fall back to the bundled .txt file.
    """
    from django.db import DatabaseError

    from backend.conversation.models import ConversationLLMPrompt

    row = None
    try:
        row = (
            ConversationLLMPrompt.objects.filter(key=key)
            .order_by("id")
            .first()
        )
    except DatabaseError:
        row = None
    if row is not None:
        return PromptPair(
            key=row.key,
            system_template=row.system_template,
            user_template=row.user_template,
        )
    data = load_prompt_blocks_from_file()
    if key not in data:
        msg = f"No prompt for key {key!r} in DB or {default_prompts_path()}"
        raise ValueError(msg)
    return data[key]


def seed_conversation_llm_prompts(*, dry_run: bool = False) -> list[str]:
    """
    Upsert ConversationLLMPrompt rows from the bundled conversation_llm_prompts.txt.
    Returns human-readable log lines. Used by init_llm_seed.
    """
    from backend.conversation.models import ConversationLLMPrompt

    data = load_prompt_blocks_from_file()
    changes: list[str] = []
    for key, pair in data.items():
        obj = (
            ConversationLLMPrompt.objects.filter(key=key)
            .order_by("id")
            .first()
        )
        created = obj is None
        if obj is None:
            obj = ConversationLLMPrompt(
                key=key,
                system_template=pair.system_template,
                user_template=pair.user_template,
            )
        else:
            obj.system_template = pair.system_template
            obj.user_template = pair.user_template

        changes.append(
            f"ConversationLLMPrompt {'CREATE' if created else 'UPDATE'} {key}",
        )
        if not dry_run:
            obj.save()
    return changes

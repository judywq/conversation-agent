import json
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from langchain_core.messages import SystemMessage

from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.tts import synthesize_speech

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def generate_cefr_topic_samples(*, topic: str, voice: str = "alloy") -> list[dict[str, str]]:
    template = load_additional_prompt("cefr_topic_samples.txt")
    prompt_text = render_prompt_template(template, topic=topic)
    llm = get_default_chat_llm()
    result = llm.invoke([SystemMessage(content=prompt_text)])
    raw = result.content if hasattr(result, "content") else str(result)

    parsed_samples = _parse_samples(raw)
    texts_by_level = {
        level: str(parsed_samples.get(level) or _fallback_sample_text(level=level, topic=topic))
        for level in CEFR_LEVELS
    }

    def synthesize_level(level: str) -> dict[str, str]:
        close_old_connections()
        text = texts_by_level[level]
        audio_url = synthesize_speech(text=text, voice=voice)
        return {"level": level, "text": text, "audio_url": audio_url}

    with ThreadPoolExecutor(max_workers=len(CEFR_LEVELS)) as executor:
        return list(executor.map(synthesize_level, CEFR_LEVELS))


def _parse_samples(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    samples = parsed.get("samples") if isinstance(parsed, dict) else None
    if not isinstance(samples, list):
        return {}

    out: dict[str, str] = {}
    for item in samples:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or "").upper()
        text = str(item.get("text") or "").strip()
        if level in CEFR_LEVELS and text:
            out[level] = text
    return out


def _fallback_sample_text(*, level: str, topic: str) -> str:
    return (
        f"This discussion is about {topic}. "
        f"This {level} sample helps you decide whether the listening level feels comfortable."
    )

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from django.db import close_old_connections
from langchain_core.messages import SystemMessage

from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.tts import synthesize_speech

logger = logging.getLogger(__name__)

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def _audio_url_log_hint(audio_url: str) -> str:
    if not audio_url:
        return ""
    if "://" in audio_url:
        path = urlparse(audio_url).path
        return path.rsplit("/", 1)[-1] if path else urlparse(audio_url).netloc
    return audio_url.rsplit("/", 1)[-1]


def generate_cefr_topic_samples(*, topic: str, voice: str = "alloy") -> list[dict[str, str]]:
    t_pipeline0 = time.perf_counter()
    topic_log = topic[:200]
    logger.info("cefr_samples pipeline_start topic=%s voice=%s", topic_log, voice)

    t_prompt0 = time.perf_counter()
    try:
        template = load_additional_prompt("cefr_topic_samples.txt")
        prompt_text = render_prompt_template(template, topic=topic)
    except Exception:
        logger.exception(
            "cefr_samples pipeline_failed step=prompt topic=%s total_ms=%d",
            topic_log,
            int((time.perf_counter() - t_pipeline0) * 1000),
        )
        raise
    prompt_ms = int((time.perf_counter() - t_prompt0) * 1000)
    logger.info(
        "cefr_samples prompt_ready topic=%s duration_ms=%d prompt_chars=%d",
        topic_log,
        prompt_ms,
        len(prompt_text),
    )

    logger.info("cefr_samples llm_start topic=%s", topic_log)
    t_llm0 = time.perf_counter()
    try:
        llm = get_default_chat_llm()
        result = llm.invoke([SystemMessage(content=prompt_text)])
        raw = result.content if hasattr(result, "content") else str(result)
    except Exception:
        logger.exception(
            "cefr_samples pipeline_failed step=llm topic=%s total_ms=%d",
            topic_log,
            int((time.perf_counter() - t_pipeline0) * 1000),
        )
        raise
    llm_ms = int((time.perf_counter() - t_llm0) * 1000)
    logger.info(
        "cefr_samples llm_complete topic=%s duration_ms=%d raw_chars=%d",
        topic_log,
        llm_ms,
        len(raw),
    )

    t_parse0 = time.perf_counter()
    parsed_samples = _parse_samples(raw)
    texts_by_level = {
        level: str(parsed_samples.get(level) or _fallback_sample_text(level=level, topic=topic))
        for level in CEFR_LEVELS
    }
    levels_from_llm = sum(1 for level in CEFR_LEVELS if level in parsed_samples)
    levels_using_fallback = len(CEFR_LEVELS) - levels_from_llm
    parse_ms = int((time.perf_counter() - t_parse0) * 1000)
    logger.info(
        "cefr_samples parse_complete topic=%s duration_ms=%d levels_from_llm=%d levels_using_fallback=%d",
        topic_log,
        parse_ms,
        levels_from_llm,
        levels_using_fallback,
    )

    level_timings: dict[str, int] = {}

    def synthesize_level(level: str) -> dict[str, str]:
        close_old_connections()
        thread_name = threading.current_thread().name
        text = texts_by_level[level]
        logger.info(
            "cefr_samples tts_level_start topic=%s level=%s text_chars=%d thread=%s",
            topic_log,
            level,
            len(text),
            thread_name,
        )
        t_level0 = time.perf_counter()
        try:
            audio_url = synthesize_speech(text=text, voice=voice)
        except Exception:
            level_ms = int((time.perf_counter() - t_level0) * 1000)
            level_timings[level] = level_ms
            logger.exception(
                "cefr_samples tts_level_failed topic=%s level=%s duration_ms=%d thread=%s",
                topic_log,
                level,
                level_ms,
                thread_name,
            )
            raise
        level_ms = int((time.perf_counter() - t_level0) * 1000)
        level_timings[level] = level_ms
        logger.info(
            "cefr_samples tts_level_complete topic=%s level=%s duration_ms=%d text_chars=%d audio_path=%s thread=%s",
            topic_log,
            level,
            level_ms,
            len(text),
            _audio_url_log_hint(audio_url),
            thread_name,
        )
        return {"level": level, "text": text, "audio_url": audio_url}

    logger.info(
        "cefr_samples tts_pool_start topic=%s level_count=%d",
        topic_log,
        len(CEFR_LEVELS),
    )
    t_pool0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=len(CEFR_LEVELS)) as executor:
            samples = list(executor.map(synthesize_level, CEFR_LEVELS))
    except Exception:
        logger.exception(
            "cefr_samples pipeline_failed step=tts_pool topic=%s total_ms=%d",
            topic_log,
            int((time.perf_counter() - t_pipeline0) * 1000),
        )
        raise
    pool_ms = int((time.perf_counter() - t_pool0) * 1000)
    slowest_level = max(level_timings, key=level_timings.get) if level_timings else ""
    slowest_ms = level_timings.get(slowest_level, 0)
    logger.info(
        "cefr_samples tts_pool_complete topic=%s duration_ms=%d slowest_level=%s slowest_ms=%d",
        topic_log,
        pool_ms,
        slowest_level,
        slowest_ms,
    )

    total_ms = int((time.perf_counter() - t_pipeline0) * 1000)
    logger.info("cefr_samples pipeline_complete topic=%s total_ms=%d", topic_log, total_ms)
    return samples


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

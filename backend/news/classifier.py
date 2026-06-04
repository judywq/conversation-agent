from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from langchain_core.messages import SystemMessage

from backend.conversation.services.llm import get_default_chat_llm

from .models import NewsArticle
from .models import NewsClassification
from .taxonomy import NEWS_TAXONOMY
from .taxonomy import TAXONOMY_VERSION
from .taxonomy import get_category
from .taxonomy import get_subtopic

MIN_MARKDOWN_FENCE_LINE_COUNT = 3


def classify_article(
    article: NewsArticle,
    *,
    llm: Any | None = None,
    llm_model: str = "",
) -> NewsClassification:
    llm = llm or get_default_chat_llm()
    try:
        result = llm.invoke(
            [SystemMessage(content=build_classification_prompt(article))],
        )
        payload = parse_classification_payload(str(result.content))
        validate_classification_payload(payload)
    except Exception as exc:  # noqa: BLE001
        return save_failed_classification(article, error=str(exc), llm_model=llm_model)

    return save_successful_classification(article, payload=payload, llm_model=llm_model)


def build_classification_prompt(article: NewsArticle) -> str:
    taxonomy_lines = []
    for category in NEWS_TAXONOMY:
        subtopic_slugs = ", ".join(subtopic.slug for subtopic in category.subtopics)
        taxonomy_lines.append(f"- {category.slug}: {subtopic_slugs}")

    return (
        "Classify this news article for an English learning system.\n"
        "Return strict JSON only with keys: main_category, subtopics, cefr_level, "
        "is_suitable, confidence, rationale.\n"
        "Use only these taxonomy values:\n"
        f"{chr(10).join(taxonomy_lines)}\n\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary}\n"
        f"Source: {article.feed_title}\n"
        f"Published at: {article.published_at.isoformat()}\n"
    )


def parse_classification_payload(raw_content: str) -> dict[str, Any]:
    raw_content = strip_markdown_json_fence(raw_content)
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON classification output: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = "JSON classification output must be an object"
        raise TypeError(msg)
    return payload


def strip_markdown_json_fence(raw_content: str) -> str:
    content = raw_content.strip()
    if not content.startswith("```") or not content.endswith("```"):
        return content

    lines = content.splitlines()
    if len(lines) < MIN_MARKDOWN_FENCE_LINE_COUNT:
        return content
    opening = lines[0].strip().lower()
    if opening not in {"```", "```json"}:
        return content
    return "\n".join(lines[1:-1]).strip()


def validate_classification_payload(payload: dict[str, Any]) -> None:
    main_category = str(payload.get("main_category") or "")
    get_category(main_category)

    subtopics = payload.get("subtopics") or []
    if not isinstance(subtopics, list):
        msg = "subtopics must be a list"
        raise TypeError(msg)
    for subtopic in subtopics:
        get_subtopic(main_category, str(subtopic))

    confidence = Decimal(str(payload.get("confidence", "0")))
    if confidence < 0 or confidence > 1:
        msg = "confidence must be between 0 and 1"
        raise ValueError(msg)


def save_successful_classification(
    article: NewsArticle,
    *,
    payload: dict[str, Any],
    llm_model: str,
) -> NewsClassification:
    classification, _ = NewsClassification.objects.update_or_create(
        article=article,
        taxonomy_version=TAXONOMY_VERSION,
        defaults={
            "main_category": payload["main_category"],
            "subtopics": payload.get("subtopics") or [],
            "cefr_level": payload.get("cefr_level") or "",
            "is_suitable": bool(payload.get("is_suitable")),
            "confidence": Decimal(str(payload.get("confidence", "0"))),
            "rationale": payload.get("rationale") or "",
            "llm_model": llm_model,
            "status": NewsClassification.Status.SUCCEEDED,
            "error_message": "",
            "raw_output": payload,
        },
    )
    return classification


def save_failed_classification(
    article: NewsArticle,
    *,
    error: str,
    llm_model: str,
) -> NewsClassification:
    classification, _ = NewsClassification.objects.update_or_create(
        article=article,
        taxonomy_version=TAXONOMY_VERSION,
        defaults={
            "main_category": "",
            "subtopics": [],
            "cefr_level": "",
            "is_suitable": False,
            "confidence": None,
            "rationale": "",
            "llm_model": llm_model,
            "status": NewsClassification.Status.FAILED,
            "error_message": error,
            "raw_output": {},
        },
    )
    return classification

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from django.conf import settings
from langchain_core.messages import SystemMessage

from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.llm import get_default_chat_llm
from backend.news.classifier import classify_article
from backend.news.full_text import fetch_and_store_full_text
from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.sync import sync_recent_articles
from backend.news.taxonomy import TAXONOMY_VERSION
from backend.news.taxonomy import get_category
from backend.news.taxonomy import get_subtopic

logger = logging.getLogger(__name__)

DISCUSSION_ARTICLE_LIMIT = 5


@dataclass(frozen=True)
class DiscussionArticleContext:
    id: int
    title: str
    summary: str
    url: str
    full_text_fetched: bool = False


@dataclass(frozen=True)
class DiscussionScenarioResult:
    scenario: str
    category: str
    subtopic: str
    category_name: str
    subtopic_name: str
    article_id: int | None = None
    article_title: str = ""
    article_ids: list[int] = field(default_factory=list)
    articles: list[DiscussionArticleContext] = field(default_factory=list)


def fetch_context_articles(
    *,
    category: str,
    subtopic: str,
    limit: int = DISCUSSION_ARTICLE_LIMIT,
    cefr_level: str | None = None,
) -> list[NewsArticle]:
    queryset = NewsClassification.objects.filter(
        main_category=category,
        status=NewsClassification.Status.SUCCEEDED,
        is_suitable=True,
        subtopics__contains=[subtopic],
        article__status=NewsArticle.Status.IMPORTED,
    )
    if cefr_level:
        queryset = queryset.filter(cefr_level=str(cefr_level).upper())
    classifications = (
        queryset.select_related("article")
        .order_by("-article__published_at", "-article_id")[:limit]
    )
    return [classification.article for classification in classifications]


def ensure_articles_for_taxonomy(
    *,
    category: str,
    subtopic: str,
    limit: int = DISCUSSION_ARTICLE_LIMIT,
    cefr_level: str | None = None,
) -> list[NewsArticle]:
    articles = fetch_context_articles(
        category=category,
        subtopic=subtopic,
        limit=limit,
        cefr_level=cefr_level,
    )
    if articles:
        return articles

    sync_recent_articles(limit=int(getattr(settings, "NEWS_SYNC_BATCH_SIZE", 100)))
    successfully_classified_ids = NewsClassification.objects.filter(
        taxonomy_version=TAXONOMY_VERSION,
        status=NewsClassification.Status.SUCCEEDED,
    ).values("article_id")
    unclassified = NewsArticle.objects.exclude(
        id__in=successfully_classified_ids,
    ).order_by("-published_at")[
        : int(getattr(settings, "NEWS_CLASSIFICATION_BATCH_SIZE", 25))
    ]
    for article in unclassified:
        classify_article(article)

    return fetch_context_articles(
        category=category,
        subtopic=subtopic,
        limit=limit,
        cefr_level=cefr_level,
    )


def fetch_context_article(*, category: str, subtopic: str) -> NewsArticle | None:
    articles = fetch_context_articles(category=category, subtopic=subtopic, limit=1)
    return articles[0] if articles else None


def _build_news_context(articles: list[NewsArticle]) -> str:
    if not articles:
        return "No classified articles available yet for this subtopic."

    blocks: list[str] = []
    for index, article in enumerate(articles, start=1):
        parts = [f"Article {index}:", f"Title: {article.title}"]
        if article.summary:
            parts.append(f"Summary: {article.summary}")
        if article.source_title or article.feed_title:
            parts.append(f"Source: {article.source_title or article.feed_title}")
        if article.url:
            parts.append(f"URL: {article.url}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _article_contexts(articles: list[NewsArticle]) -> list[DiscussionArticleContext]:
    return [
        DiscussionArticleContext(
            id=article.id,
            title=article.title,
            summary=article.summary,
            url=article.url,
            full_text_fetched=bool((article.full_text or "").strip()),
        )
        for article in articles
    ]


def _parse_scenario_payload(raw: str) -> str:
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if len(lines) >= 3:
            content = "\n".join(lines[1:-1]).strip()
    payload = json.loads(content)
    if not isinstance(payload, dict):
        msg = "Scenario JSON must be an object"
        raise TypeError(msg)
    scenario = str(payload.get("scenario") or "").strip()
    if not scenario:
        msg = "Scenario JSON missing scenario text"
        raise ValueError(msg)
    return scenario


def generate_discussion_scenario_from_articles(
    *,
    category: str,
    subtopic: str,
    articles: list[NewsArticle],
) -> DiscussionScenarioResult:
    category_obj = get_category(category)
    subtopic_obj = get_subtopic(category, subtopic)
    template = load_additional_prompt("discussion_scenario.txt")
    prompt_text = render_prompt_template(
        template,
        category_name=category_obj.name,
        subtopic_name=subtopic_obj.name,
        subtopic_keywords=", ".join(subtopic_obj.keywords),
        news_context=_build_news_context(articles),
    )
    llm = get_default_chat_llm()
    result = llm.invoke([SystemMessage(content=prompt_text)])
    raw = result.content if hasattr(result, "content") else str(result)
    scenario = _parse_scenario_payload(str(raw))
    primary = articles[0] if articles else None
    article_ids = [article.id for article in articles]
    logger.info(
        "discussion_scenario_generated category=%s subtopic=%s article_ids=%s chars=%d",
        category,
        subtopic,
        article_ids,
        len(scenario),
    )
    return DiscussionScenarioResult(
        scenario=scenario,
        category=category,
        subtopic=subtopic,
        category_name=category_obj.name,
        subtopic_name=subtopic_obj.name,
        article_id=primary.id if primary else None,
        article_title=primary.title if primary else "",
        article_ids=article_ids,
        articles=_article_contexts(articles),
    )


def setup_discussion_context(
    *,
    category: str,
    subtopic: str,
    cefr_level: str | None = None,
    limit: int = DISCUSSION_ARTICLE_LIMIT,
) -> DiscussionScenarioResult:
    articles = ensure_articles_for_taxonomy(
        category=category,
        subtopic=subtopic,
        limit=limit,
        cefr_level=cefr_level,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        scenario_future = executor.submit(
            generate_discussion_scenario_from_articles,
            category=category,
            subtopic=subtopic,
            articles=articles,
        )
        fulltext_future = executor.submit(fetch_and_store_full_text, articles)
        result = scenario_future.result()
        updated_articles = fulltext_future.result()

    refreshed = list(
        NewsArticle.objects.filter(id__in=[article.id for article in updated_articles]).order_by(
            "-published_at",
            "-id",
        ),
    )
    return DiscussionScenarioResult(
        scenario=result.scenario,
        category=result.category,
        subtopic=result.subtopic,
        category_name=result.category_name,
        subtopic_name=result.subtopic_name,
        article_id=result.article_id,
        article_title=result.article_title,
        article_ids=result.article_ids,
        articles=_article_contexts(refreshed),
    )


def generate_discussion_scenario(*, category: str, subtopic: str) -> DiscussionScenarioResult:
    return setup_discussion_context(category=category, subtopic=subtopic)


def scenario_result_to_dict(result: DiscussionScenarioResult) -> dict[str, Any]:
    return {
        "scenario": result.scenario,
        "category": result.category,
        "subtopic": result.subtopic,
        "category_name": result.category_name,
        "subtopic_name": result.subtopic_name,
        "article_id": result.article_id,
        "article_title": result.article_title,
        "article_ids": result.article_ids,
        "articles": [
            {
                "id": article.id,
                "title": article.title,
                "summary": article.summary,
                "url": article.url,
                "full_text_fetched": article.full_text_fetched,
            }
            for article in result.articles
        ],
    }

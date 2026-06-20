from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Literal

from django.conf import settings
from langchain_core.messages import SystemMessage

from backend.conversation.prompts import load_additional_prompt
from backend.conversation.prompts import render_prompt_template
from backend.conversation.services.cefr_levels import normalize_user_cefr_level
from backend.conversation.services.llm import get_default_chat_llm
from backend.conversation.services.web_search import build_scenario_knowledge_query
from backend.conversation.services.web_search import fetch_web_search_context
from backend.conversation.services.web_search import web_search_context_is_usable
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
KnowledgeSource = Literal["articles", "web", "none"]

ARTICLE_MODE_INSTRUCTIONS = (
    "If multiple articles are provided, synthesize themes across them; you may generalize beyond any single article.\n"
    "Use only the article summaries provided; do not invent additional article details."
)
SUBTOPIC_MODE_INSTRUCTIONS = (
    "No news articles are available for this subtopic.\n"
    "Create a plausible discussion scenario using only the category, subtopic, and keywords above.\n"
    "Do not claim specific news events, dates, or statistics."
)


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
    web_context: str = ""
    knowledge_source: KnowledgeSource = "none"
    web_context_fetched: bool = False


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


def _cefr_language_guidance(cefr_level: str) -> str:
    if cefr_level in ("A1", "A2"):
        return (
            "Use very short sentences and high-frequency vocabulary suitable for beginner learners."
        )
    if cefr_level in ("C1", "C2"):
        return (
            "You may use more nuanced debate framing and slightly more complex syntax for advanced learners."
        )
    return (
        "Use clear intermediate English (B1): straightforward sentences and common academic vocabulary."
    )


def generate_scenario_with_llm(
    *,
    category: str,
    subtopic: str,
    articles: list[NewsArticle],
    cefr_level: str | None = None,
) -> DiscussionScenarioResult:
    category_obj = get_category(category)
    subtopic_obj = get_subtopic(category, subtopic)
    normalized_cefr = normalize_user_cefr_level(cefr_level)
    has_articles = bool(articles)
    template = load_additional_prompt("discussion_scenario.txt")
    prompt_text = render_prompt_template(
        template,
        category_name=category_obj.name,
        subtopic_name=subtopic_obj.name,
        subtopic_keywords=", ".join(subtopic_obj.keywords),
        cefr_level=normalized_cefr,
        cefr_language_guidance=_cefr_language_guidance(normalized_cefr),
        mode_instructions=ARTICLE_MODE_INSTRUCTIONS if has_articles else SUBTOPIC_MODE_INSTRUCTIONS,
        news_context=_build_news_context(articles) if has_articles else "Not applicable.",
    )
    llm = get_default_chat_llm()
    result = llm.invoke([SystemMessage(content=prompt_text)])
    raw = result.content if hasattr(result, "content") else str(result)
    scenario = _parse_scenario_payload(str(raw))
    primary = articles[0] if articles else None
    article_ids = [article.id for article in articles]
    logger.info(
        "discussion_scenario_generated category=%s subtopic=%s article_ids=%s cefr=%s chars=%d",
        category,
        subtopic,
        article_ids,
        normalized_cefr,
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
        knowledge_source="articles" if has_articles else "none",
    )


def generate_discussion_scenario_from_articles(
    *,
    category: str,
    subtopic: str,
    articles: list[NewsArticle],
    cefr_level: str | None = None,
) -> DiscussionScenarioResult:
    return generate_scenario_with_llm(
        category=category,
        subtopic=subtopic,
        articles=articles,
        cefr_level=cefr_level,
    )


def _fetch_web_context_for_scenario(
    *,
    category_name: str,
    subtopic_name: str,
    scenario: str,
) -> tuple[str, bool]:
    query = build_scenario_knowledge_query(
        category_name=category_name,
        subtopic_name=subtopic_name,
        scenario=scenario,
    )
    web_context = fetch_web_search_context(query)
    usable = web_search_context_is_usable(web_context)
    return (web_context if usable else ""), usable


def setup_discussion_context(
    *,
    category: str,
    subtopic: str,
    cefr_level: str | None = None,
    limit: int = DISCUSSION_ARTICLE_LIMIT,
) -> DiscussionScenarioResult:
    normalized_cefr = normalize_user_cefr_level(cefr_level)
    articles = ensure_articles_for_taxonomy(
        category=category,
        subtopic=subtopic,
        limit=limit,
        cefr_level=normalized_cefr,
    )

    if articles:
        with ThreadPoolExecutor(max_workers=2) as executor:
            scenario_future = executor.submit(
                generate_scenario_with_llm,
                category=category,
                subtopic=subtopic,
                articles=articles,
                cefr_level=normalized_cefr,
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
            web_context="",
            knowledge_source="articles",
            web_context_fetched=False,
        )

    result = generate_scenario_with_llm(
        category=category,
        subtopic=subtopic,
        articles=[],
        cefr_level=normalized_cefr,
    )
    web_context, web_context_fetched = _fetch_web_context_for_scenario(
        category_name=result.category_name,
        subtopic_name=result.subtopic_name,
        scenario=result.scenario,
    )
    knowledge_source: KnowledgeSource = "web" if web_context_fetched else "none"
    return DiscussionScenarioResult(
        scenario=result.scenario,
        category=result.category,
        subtopic=result.subtopic,
        category_name=result.category_name,
        subtopic_name=result.subtopic_name,
        article_id=None,
        article_title="",
        article_ids=[],
        articles=[],
        web_context=web_context,
        knowledge_source=knowledge_source,
        web_context_fetched=web_context_fetched,
    )


def generate_discussion_scenario(*, category: str, subtopic: str, cefr_level: str | None = None) -> DiscussionScenarioResult:
    return setup_discussion_context(category=category, subtopic=subtopic, cefr_level=cefr_level)


DISCUSSION_PROFILE_FIELDS = (
    "discussion_category",
    "discussion_subtopic",
    "discussion_scenario",
    "discussion_article_id",
    "discussion_article_ids",
    "discussion_web_context",
)


def apply_discussion_result_to_profile(profile, result: DiscussionScenarioResult) -> None:
    profile.discussion_category = result.category
    profile.discussion_subtopic = result.subtopic
    profile.discussion_scenario = result.scenario
    profile.discussion_article_id = result.article_id
    profile.discussion_article_ids = result.article_ids
    profile.discussion_web_context = result.web_context if result.knowledge_source == "web" else ""


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
        "web_context": result.web_context,
        "knowledge_source": result.knowledge_source,
        "web_context_fetched": result.web_context_fetched,
    }

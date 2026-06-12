import json

import pytest
from django.utils import timezone

from backend.conversation.services.discussion_scenario import _build_news_context
from backend.conversation.services.discussion_scenario import fetch_context_articles
from backend.conversation.services.discussion_scenario import generate_discussion_scenario_from_articles
from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.taxonomy import TAXONOMY_VERSION


def _create_article(*, entry_id: int, title: str, summary: str, published_at) -> NewsArticle:
    return NewsArticle.objects.create(
        miniflux_entry_id=entry_id,
        miniflux_feed_id=1,
        feed_title="Feed",
        title=title,
        summary=summary,
        url=f"https://example.com/{entry_id}",
        normalized_url=f"https://example.com/{entry_id}",
        published_at=published_at,
    )


@pytest.mark.django_db
def test_fetch_context_articles_orders_by_published_at():
    older = _create_article(
        entry_id=701,
        title="Older",
        summary="Older summary",
        published_at=timezone.now() - timezone.timedelta(days=2),
    )
    newer = _create_article(
        entry_id=702,
        title="Newer",
        summary="Newer summary",
        published_at=timezone.now(),
    )
    for article in (older, newer):
        NewsClassification.objects.create(
            article=article,
            taxonomy_version=TAXONOMY_VERSION,
            main_category="technology-ai",
            subtopics=["ai-teachers"],
            status=NewsClassification.Status.SUCCEEDED,
        )

    articles = fetch_context_articles(
        category="technology-ai",
        subtopic="ai-teachers",
        limit=5,
    )

    assert [article.id for article in articles] == [newer.id, older.id]


@pytest.mark.django_db
def test_build_news_context_uses_summaries_only():
    article = _create_article(
        entry_id=703,
        title="Title",
        summary="Summary only.",
        published_at=timezone.now(),
    )
    article.full_text = "This full text must not appear."
    context = _build_news_context([article])
    assert "Summary only." in context
    assert "This full text must not appear." not in context


@pytest.mark.django_db
def test_generate_discussion_scenario_from_articles_uses_multiple_summaries(monkeypatch):
    articles = [
        _create_article(
            entry_id=704,
            title="First",
            summary="First summary.",
            published_at=timezone.now(),
        ),
        _create_article(
            entry_id=705,
            title="Second",
            summary="Second summary.",
            published_at=timezone.now() - timezone.timedelta(hours=1),
        ),
    ]

    captured = {}

    class FakeLLM:
        def invoke(self, messages):
            captured["prompt"] = messages[0].content
            return type("Result", (), {"content": json.dumps({"scenario": "Discuss both articles."})})()

    monkeypatch.setattr(
        "backend.conversation.services.discussion_scenario.get_default_chat_llm",
        lambda: FakeLLM(),
    )

    result = generate_discussion_scenario_from_articles(
        category="technology-ai",
        subtopic="ai-teachers",
        articles=articles,
    )

    assert result.article_ids == [article.id for article in articles]
    assert "First summary." in captured["prompt"]
    assert "Second summary." in captured["prompt"]
    assert "full text" not in captured["prompt"].lower()

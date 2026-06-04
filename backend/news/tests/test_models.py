from decimal import Decimal

# ruff: noqa: E501
import pytest
from django.db import IntegrityError
from django.utils import timezone

from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.taxonomy import TAXONOMY_VERSION


@pytest.mark.django_db
def test_news_article_stores_miniflux_metadata_without_full_text():
    article = NewsArticle.objects.create(
        miniflux_entry_id=123,
        miniflux_feed_id=7,
        feed_title="NPR Topics: Education",
        source_title="NPR",
        source_url="https://www.npr.org/",
        title="Students test AI tutors",
        summary="A short summary from the feed.",
        url="https://example.com/news/ai-tutors",
        normalized_url="https://example.com/news/ai-tutors",
        published_at=timezone.now(),
        raw_metadata={"category": {"title": "Education & Learning"}},
    )

    assert article.status == NewsArticle.Status.IMPORTED
    assert article.full_text == ""
    assert article.raw_metadata["category"]["title"] == "Education & Learning"


@pytest.mark.django_db
def test_news_article_rejects_duplicate_miniflux_entry_id():
    payload = {
        "miniflux_entry_id": 456,
        "miniflux_feed_id": 1,
        "feed_title": "Feed",
        "title": "Title",
        "summary": "Summary",
        "url": "https://example.com/a",
        "normalized_url": "https://example.com/a",
        "published_at": timezone.now(),
    }
    NewsArticle.objects.create(**payload)

    with pytest.raises(IntegrityError):
        NewsArticle.objects.create(**payload | {"url": "https://example.com/b", "normalized_url": "https://example.com/b"})


@pytest.mark.django_db
def test_news_article_rejects_duplicate_normalized_url():
    payload = {
        "miniflux_feed_id": 1,
        "feed_title": "Feed",
        "title": "Title",
        "summary": "Summary",
        "normalized_url": "https://example.com/same",
        "published_at": timezone.now(),
    }
    NewsArticle.objects.create(**payload, miniflux_entry_id=1, url="https://example.com/same?utm=1")

    with pytest.raises(IntegrityError):
        NewsArticle.objects.create(**payload, miniflux_entry_id=2, url="https://example.com/same?utm=2")


@pytest.mark.django_db
def test_news_classification_records_llm_output():
    article = NewsArticle.objects.create(
        miniflux_entry_id=789,
        miniflux_feed_id=2,
        feed_title="NPR Topics: Technology",
        title="AI tutors enter classrooms",
        summary="A short summary.",
        url="https://example.com/ai-classrooms",
        normalized_url="https://example.com/ai-classrooms",
        published_at=timezone.now(),
    )

    classification = NewsClassification.objects.create(
        article=article,
        taxonomy_version=TAXONOMY_VERSION,
        main_category="technology-ai",
        subtopics=["ai-teachers"],
        cefr_level="B1",
        is_suitable=True,
        confidence=Decimal("0.82"),
        rationale="The article is about AI tutors in classrooms.",
        llm_model="fake-classifier",
        raw_output={"main_category": "technology-ai"},
    )

    assert classification.status == NewsClassification.Status.SUCCEEDED
    assert classification.subtopics == ["ai-teachers"]
    assert classification.is_ready_for_learning is True

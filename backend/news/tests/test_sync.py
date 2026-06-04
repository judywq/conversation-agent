import pytest

# ruff: noqa: E501
from django.utils import timezone

from backend.news.miniflux import MinifluxConfigError
from backend.news.miniflux import MinifluxRequestError
from backend.news.models import NewsArticle
from backend.news.sync import sync_recent_articles


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"entries": []}
        self.error = error

    def fetch_recent_entries(self, *, limit):
        if self.error:
            raise self.error
        return self.payload


def miniflux_entry(**overrides):
    payload = {
        "id": 101,
        "title": "AI tutors enter classrooms",
        "content": "<p>Feed summary</p>",
        "url": "https://example.com/article?utm_source=rss",
        "published_at": "2026-06-03T10:30:00Z",
        "feed": {
            "id": 5,
            "title": "NPR Topics: Technology",
            "site_url": "https://www.npr.org/",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_sync_recent_articles_creates_new_article():
    result = sync_recent_articles(client=FakeClient({"entries": [miniflux_entry()]}), limit=10)

    article = NewsArticle.objects.get(miniflux_entry_id=101)
    assert result.created_count == 1
    assert article.title == "AI tutors enter classrooms"
    assert article.summary == "Feed summary"
    assert article.normalized_url == "https://example.com/article"
    assert article.feed_title == "NPR Topics: Technology"
    assert article.source_url == "https://www.npr.org/"
    assert article.full_text == ""


@pytest.mark.django_db
def test_sync_recent_articles_updates_existing_entry_without_duplicate():
    NewsArticle.objects.create(
        miniflux_entry_id=101,
        miniflux_feed_id=5,
        feed_title="Old feed",
        title="Old title",
        summary="Old summary",
        url="https://example.com/article",
        normalized_url="https://example.com/article",
        published_at=timezone.now(),
    )

    result = sync_recent_articles(
        client=FakeClient({"entries": [miniflux_entry(title="Updated title")]}),
        limit=10,
    )

    assert result.created_count == 0
    assert result.updated_count == 1
    assert NewsArticle.objects.count() == 1
    assert NewsArticle.objects.get().title == "Updated title"


@pytest.mark.django_db
def test_sync_recent_articles_skips_duplicate_normalized_url_from_different_entry():
    NewsArticle.objects.create(
        miniflux_entry_id=101,
        miniflux_feed_id=5,
        feed_title="Original feed",
        title="Original",
        summary="Summary",
        url="https://example.com/article",
        normalized_url="https://example.com/article",
        published_at=timezone.now(),
    )

    result = sync_recent_articles(
        client=FakeClient({"entries": [miniflux_entry(id=202, title="Duplicate from another feed")]}),
        limit=10,
    )

    assert result.created_count == 0
    assert result.duplicate_url_count == 1
    assert NewsArticle.objects.count() == 1


@pytest.mark.django_db
def test_sync_recent_articles_preserves_existing_articles_when_miniflux_fails():
    NewsArticle.objects.create(
        miniflux_entry_id=101,
        miniflux_feed_id=5,
        feed_title="Existing feed",
        title="Existing",
        summary="Summary",
        url="https://example.com/existing",
        normalized_url="https://example.com/existing",
        published_at=timezone.now(),
    )

    result = sync_recent_articles(
        client=FakeClient(error=MinifluxRequestError("boom")),
        limit=10,
    )

    assert result.failed is True
    assert NewsArticle.objects.count() == 1


@pytest.mark.django_db
def test_sync_recent_articles_returns_failure_when_miniflux_config_missing(
    monkeypatch,
):
    def fake_from_settings():
        msg = "MINIFLUX_BASE_URL is required"
        raise MinifluxConfigError(msg)

    monkeypatch.setattr(
        "backend.news.sync.MinifluxClient.from_settings",
        fake_from_settings,
    )

    result = sync_recent_articles(limit=10)

    assert result.failed is True
    assert "MINIFLUX_BASE_URL is required" in result.error
    assert NewsArticle.objects.count() == 0

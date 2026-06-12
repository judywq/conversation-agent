from dataclasses import dataclass
from datetime import timedelta

from celery.result import EagerResult
from django.utils import timezone

from backend.news.models import NewsArticle
from backend.news.models import NewsClassification
from backend.news.tasks import classify_unclassified_news
from backend.news.tasks import sync_miniflux_news
from backend.news.taxonomy import TAXONOMY_VERSION


@dataclass(frozen=True)
class FakeSyncResult:
    created_count: int = 1
    updated_count: int = 2
    duplicate_url_count: int = 3
    failed: bool = False
    error: str = ""


def test_sync_miniflux_news_task_calls_sync(monkeypatch, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    calls = []

    def fake_sync_recent_articles(*, limit):
        calls.append(limit)
        return FakeSyncResult()

    monkeypatch.setattr(
        "backend.news.tasks.sync_recent_articles",
        fake_sync_recent_articles,
    )

    result = sync_miniflux_news.delay(limit=33)

    assert isinstance(result, EagerResult)
    assert calls == [33]
    assert result.result == {
        "created_count": 1,
        "duplicate_url_count": 3,
        "failed": False,
        "updated_count": 2,
    }


def test_classify_unclassified_news_task_limits_batch(monkeypatch, settings, db):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    base_time = timezone.now()
    articles = [
        NewsArticle.objects.create(
            miniflux_entry_id=idx,
            miniflux_feed_id=1,
            feed_title="Feed",
            title=f"Article {idx}",
            summary="Summary",
            url=f"https://example.com/{idx}",
            normalized_url=f"https://example.com/{idx}",
            published_at=base_time + timedelta(minutes=idx),
        )
        for idx in range(1, 4)
    ]
    NewsClassification.objects.create(
        article=articles[0],
        taxonomy_version=TAXONOMY_VERSION,
        main_category="technology-ai",
        subtopics=[],
        status=NewsClassification.Status.SUCCEEDED,
    )
    calls = []

    def fake_classify_article(article):
        calls.append(article.id)
        return NewsClassification.objects.create(
            article=article,
            taxonomy_version=TAXONOMY_VERSION,
            main_category="technology-ai",
            subtopics=[],
            status=NewsClassification.Status.SUCCEEDED,
        )

    monkeypatch.setattr("backend.news.tasks.classify_article", fake_classify_article)

    result = classify_unclassified_news.delay(limit=1)

    assert isinstance(result, EagerResult)
    assert len(calls) == 1
    assert calls == [articles[2].id]
    assert result.result == {"classified_count": 1}


def test_classify_unclassified_news_task_retries_failed_classifications(
    monkeypatch,
    settings,
    db,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    article = NewsArticle.objects.create(
        miniflux_entry_id=10,
        miniflux_feed_id=1,
        feed_title="Feed",
        title="Retry article",
        summary="Summary",
        url="https://example.com/retry",
        normalized_url="https://example.com/retry",
        published_at=timezone.now(),
    )
    NewsClassification.objects.create(
        article=article,
        taxonomy_version=TAXONOMY_VERSION,
        main_category="",
        subtopics=[],
        status=NewsClassification.Status.FAILED,
        error_message="temporary provider failure",
    )
    calls = []

    def fake_classify_article(article):
        calls.append(article.id)
        return NewsClassification.objects.update_or_create(
            article=article,
            taxonomy_version=TAXONOMY_VERSION,
            defaults={
                "main_category": "technology-ai",
                "subtopics": [],
                "status": NewsClassification.Status.SUCCEEDED,
            },
        )[0]

    monkeypatch.setattr("backend.news.tasks.classify_article", fake_classify_article)

    result = classify_unclassified_news.delay(limit=1)

    assert calls == [article.id]
    assert result.result == {"classified_count": 1}
    assert article.classifications.get().status == NewsClassification.Status.SUCCEEDED

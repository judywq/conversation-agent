# ruff: noqa: PLR2004

from django.conf import settings


def test_miniflux_settings_have_safe_defaults():
    assert settings.MINIFLUX_BASE_URL == ""
    assert settings.MINIFLUX_API_TOKEN == ""
    assert settings.MINIFLUX_USERNAME == ""
    assert settings.MINIFLUX_PASSWORD == ""
    assert settings.MINIFLUX_TIMEOUT_SEC == 15.0
    assert settings.NEWS_SYNC_BATCH_SIZE == 100
    assert settings.NEWS_CLASSIFICATION_BATCH_SIZE == 25


def test_news_celery_beat_schedule_has_default_sync_and_classification_tasks():
    assert settings.CELERY_BEAT_SCHEDULE["sync-miniflux-news-hourly"] == {
        "task": "backend.news.tasks.sync_miniflux_news",
        "schedule": 60 * 60,
    }
    assert settings.CELERY_BEAT_SCHEDULE["classify-news-half-hourly"] == {
        "task": "backend.news.tasks.classify_unclassified_news",
        "schedule": 30 * 60,
    }

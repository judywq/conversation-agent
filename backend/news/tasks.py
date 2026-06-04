from celery import shared_task
from django.conf import settings

from .classifier import classify_article
from .models import NewsArticle
from .models import NewsClassification
from .sync import sync_recent_articles
from .taxonomy import TAXONOMY_VERSION


@shared_task()
def sync_miniflux_news(limit: int | None = None) -> dict[str, int | bool]:
    result = sync_recent_articles(limit=limit or settings.NEWS_SYNC_BATCH_SIZE)
    return {
        "created_count": result.created_count,
        "duplicate_url_count": result.duplicate_url_count,
        "failed": result.failed,
        "updated_count": result.updated_count,
    }


@shared_task()
def classify_unclassified_news(limit: int | None = None) -> dict[str, int]:
    successfully_classified_ids = NewsClassification.objects.filter(
        taxonomy_version=TAXONOMY_VERSION,
        status=NewsClassification.Status.SUCCEEDED,
    ).values("article_id")
    articles = NewsArticle.objects.exclude(
        id__in=successfully_classified_ids,
    ).order_by("-published_at")[: limit or settings.NEWS_CLASSIFICATION_BATCH_SIZE]
    count = 0
    for article in articles:
        classify_article(article)
        count += 1
    return {"classified_count": count}

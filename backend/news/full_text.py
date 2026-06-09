from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

from .miniflux import MinifluxClient
from .miniflux import MinifluxConfigError
from .miniflux import MinifluxRequestError
from .models import NewsArticle
from .sync import html_to_text

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS = 5


def _fetch_one_article_full_text(article: NewsArticle, *, client: MinifluxClient) -> NewsArticle:
    try:
        html = client.fetch_entry_content(article.miniflux_entry_id, update_content=True)
        text = html_to_text(html)
        if text:
            article.full_text = text
            article.save(update_fields=["full_text", "updated_at"])
            logger.info(
                "news_full_text_fetched article_id=%s miniflux_entry_id=%s chars=%d",
                article.id,
                article.miniflux_entry_id,
                len(text),
            )
            return article
    except (MinifluxConfigError, MinifluxRequestError) as exc:
        logger.warning(
            "news_full_text_fetch_failed article_id=%s miniflux_entry_id=%s error=%s",
            article.id,
            article.miniflux_entry_id,
            exc,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "news_full_text_fetch_failed article_id=%s miniflux_entry_id=%s",
            article.id,
            article.miniflux_entry_id,
        )

    if article.summary and not article.full_text:
        article.full_text = article.summary
        article.save(update_fields=["full_text", "updated_at"])
        logger.info(
            "news_full_text_fallback_summary article_id=%s chars=%d",
            article.id,
            len(article.summary),
        )
    return article


def fetch_and_store_full_text(
    articles: list[NewsArticle],
    *,
    client: MinifluxClient | None = None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> list[NewsArticle]:
    if not articles:
        return []

    try:
        client = client or MinifluxClient.from_settings()
    except MinifluxConfigError as exc:
        logger.warning("news_full_text_skipped_miniflux_config error=%s", exc)
        for article in articles:
            if article.summary and not article.full_text:
                article.full_text = article.summary
                article.save(update_fields=["full_text", "updated_at"])
        return articles

    updated: dict[int, NewsArticle] = {}
    workers = max(1, min(max_workers, len(articles)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_one_article_full_text, article, client=client): article.id
            for article in articles
        }
        for future in as_completed(futures):
            article = future.result()
            updated[article.id] = article

    return [updated.get(article.id, article) for article in articles]

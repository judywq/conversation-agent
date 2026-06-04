from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from .miniflux import MinifluxClient
from .miniflux import MinifluxConfigError
from .miniflux import MinifluxRequestError
from .models import NewsArticle

logger = logging.getLogger(__name__)

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class SyncResult:
    created_count: int = 0
    updated_count: int = 0
    duplicate_url_count: int = 0
    failed: bool = False
    error: str = ""


def sync_recent_articles(
    *,
    client: MinifluxClient | None = None,
    limit: int,
) -> SyncResult:
    try:
        client = client or MinifluxClient.from_settings()
        payload = client.fetch_recent_entries(limit=limit)
    except (MinifluxConfigError, MinifluxRequestError) as exc:
        logger.exception("miniflux_sync_failed")
        return SyncResult(failed=True, error=str(exc))

    created = 0
    updated = 0
    duplicate_urls = 0
    for entry in payload.get("entries", []):
        outcome = upsert_article_from_miniflux_entry(entry)
        if outcome == "created":
            created += 1
        elif outcome == "updated":
            updated += 1
        elif outcome == "duplicate_url":
            duplicate_urls += 1
    return SyncResult(
        created_count=created,
        updated_count=updated,
        duplicate_url_count=duplicate_urls,
    )


def upsert_article_from_miniflux_entry(entry: dict[str, Any]) -> str:
    miniflux_entry_id = int(entry["id"])
    article_url = entry.get("url") or ""
    normalized_url = normalize_article_url(article_url)
    feed = entry.get("feed") or {}
    published_at = parse_datetime(entry.get("published_at") or "") or now()

    defaults = {
        "miniflux_feed_id": int(feed.get("id") or 0),
        "feed_title": feed.get("title") or "",
        "source_title": feed.get("title") or "",
        "source_url": feed.get("site_url") or "",
        "title": entry.get("title") or "",
        "summary": html_to_text(entry.get("content") or entry.get("summary") or ""),
        "url": article_url,
        "normalized_url": normalized_url,
        "published_at": published_at,
        "raw_metadata": entry,
    }

    existing = NewsArticle.objects.filter(miniflux_entry_id=miniflux_entry_id).first()
    if existing:
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.save(update_fields=[*defaults.keys(), "updated_at"])
        return "updated"

    if NewsArticle.objects.filter(normalized_url=normalized_url).exists():
        return "duplicate_url"

    NewsArticle.objects.create(miniflux_entry_id=miniflux_entry_id, **defaults)
    return "created"


def normalize_article_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS
        and not key.startswith(TRACKING_QUERY_PREFIXES)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or parts.path,
            urlencode(query),
            "",
        ),
    )


def html_to_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(text).split())

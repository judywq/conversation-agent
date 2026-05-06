"""Web search orchestration for facilitator-driven retrieval.

JSON APIs should return either plain ``results`` / ``items`` / ``documents`` / ``snippets`` lists
or a top-level ``summary`` / ``text`` string. Each result object may include any of:

``title``, ``name``, ``page_title``, ``headline``, ``author``, ``byline``, ``authors``,
``organization``, ``org``, ``site_name``, ``publisher``, ``source``, ``site``, ``domain``,
``url``, ``link``, ``snippet``, ``body``, ``content``, ``description``, ``text``, ``abstract``,
``date``, ``published``, ``published_date``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _first_nonempty_str(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = obj.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list) and raw:
            parts = [str(x).strip() for x in raw if x is not None and str(x).strip()]
            if parts:
                return ", ".join(parts[:8])
    return ""


def _format_one_web_result(item: dict[str, Any], index: int) -> str:
    """Render one hit with title, author, organization, URL, and excerpt when present."""
    title = _first_nonempty_str(
        item,
        "title",
        "name",
        "page_title",
        "headline",
    )
    author = _first_nonempty_str(item, "author", "byline", "writer", "writers")
    org = _first_nonempty_str(
        item,
        "organization",
        "org",
        "organization_name",
        "site_name",
        "publisher",
        "publisher_name",
        "source",
        "source_name",
    )
    site = _first_nonempty_str(item, "site", "domain", "hostname", "host")
    url = _first_nonempty_str(item, "url", "link", "uri", "href")
    published = _first_nonempty_str(item, "date", "published", "published_date", "pub_date")
    snippet = _first_nonempty_str(
        item,
        "snippet",
        "body",
        "content",
        "description",
        "text",
        "abstract",
        "summary",
    )

    lines: list[str] = [f"{index}."]
    if title:
        lines.append(f"   Title: {title}")
    if author:
        lines.append(f"   Author: {author}")
    if org:
        lines.append(f"   Organization: {org}")
    elif site:
        lines.append(f"   Site: {site}")
    if published:
        lines.append(f"   Published: {published}")
    if url:
        lines.append(f"   URL: {url}")
    if snippet:
        lines.append(f"   Excerpt: {snippet}")

    # At least one substantive field besides the index
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def wants_web_search(retrieval_requirement: str | None) -> bool:
    r = (retrieval_requirement or "").strip().casefold().replace(" ", "_").replace("-", "_")
    return r == "web_search"


def build_web_search_query(
    *,
    topic: str,
    content_requirement: str,
    last_speaker_line: str,
) -> str:
    """
    Compose a single search query from discussion topic, facilitator content requirement,
    and the most recent speaker line (verbatim utterance).
    """
    lines: list[str] = []
    t = (topic or "").strip()
    if t:
        lines.append(f"Topic: {t}")
    c = (content_requirement or "").strip()
    if c:
        lines.append(f"Facilitator instruction: {c}")
    ls = (last_speaker_line or "").strip()
    if ls:
        lines.append(f"Latest turn: {ls}")
    return "\n".join(lines)


def _result_lists_from_dict(payload: dict[str, Any]) -> list[Any] | None:
    nested = payload.get("data")
    if isinstance(nested, dict):
        for key in ("results", "items", "documents", "snippets"):
            inner = nested.get(key)
            if isinstance(inner, list):
                return inner
    for key in ("results", "items", "documents", "snippets"):
        found = payload.get(key)
        if isinstance(found, list):
            return found
    return None


def _format_search_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        results = _result_lists_from_dict(payload)
        if isinstance(results, list) and results:
            blocks: list[str] = []
            for i, raw in enumerate(results[:12], start=1):
                if isinstance(raw, dict):
                    block = _format_one_web_result(raw, i)
                    if block:
                        blocks.append(block)
                elif isinstance(raw, str) and raw.strip():
                    blocks.append(f"{i}.\n   Excerpt: {raw.strip()}")
            if blocks:
                return "\n\n".join(blocks)

        for key in ("summary", "text", "answer", "content", "result"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        try:
            return json.dumps(payload, ensure_ascii=False)[:8000]
        except TypeError:
            return str(payload)[:8000]
    return str(payload).strip()


def fetch_web_search_context(query: str) -> str:
    """
    POST JSON ``{"query": "<query>"}`` to ``settings.WEB_SEARCH_API_URL`` and normalize the body.

    Expected response shapes: plain text, or JSON with a ``results``-like list (see module docstring)
    or top-level ``summary`` / ``text`` / ``answer`` when no structured hits exist.
    """
    enabled = getattr(settings, "WEB_SEARCH_ENABLED", False)
    url = (getattr(settings, "WEB_SEARCH_API_URL", "") or "").strip()
    if not enabled or not url:
        return "(Web search is disabled or not configured; proceed without verified external facts.)"

    q = (query or "").strip()
    if not q:
        return "(No search query could be built; proceed using discussion context only.)"

    timeout = float(getattr(settings, "WEB_SEARCH_TIMEOUT_SEC", 15.0))
    api_key = (getattr(settings, "WEB_SEARCH_API_KEY", "") or "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(
            url,
            json={"query": q},
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Web search request failed: %s", exc)
        return "(Web search failed; proceed without verified external facts.)"

    ctype = (resp.headers.get("Content-Type") or "").lower()
    text_body = (resp.text or "").strip()

    if "application/json" in ctype:
        try:
            parsed = resp.json()
        except json.JSONDecodeError:
            return text_body or "(Web search returned empty content.)"
        formatted = _format_search_payload(parsed)
        return formatted or "(Web search returned no usable snippets.)"

    return text_body or "(Web search returned empty content.)"

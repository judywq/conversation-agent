"""OpenAI web search orchestration for facilitator-driven retrieval.

OpenAI Responses API returns a message with text and URL citation annotations, plus optional
``web_search_call.action.sources`` when requested. The legacy formatter remains for tests and
for normalizing response-shaped payloads. Each result object may include any of:

``title``, ``name``, ``page_title``, ``headline``, ``author``, ``byline``, ``authors``,
``organization``, ``org``, ``site_name``, ``publisher``, ``source``, ``site``, ``domain``,
``url``, ``link``, ``snippet``, ``body``, ``content``, ``description``, ``text``, ``abstract``,
``date``, ``published``, ``published_date``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from openai import OpenAI
from openai import OpenAIError

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


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _iter_openai_citations(response: Any) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for output_item in _get_value(response, "output", []) or []:
        if _get_value(output_item, "type") != "message":
            continue
        for content in _get_value(output_item, "content", []) or []:
            for annotation in _get_value(content, "annotations", []) or []:
                if _get_value(annotation, "type") != "url_citation":
                    continue
                url = str(_get_value(annotation, "url", "") or "").strip()
                title = str(_get_value(annotation, "title", "") or "").strip()
                if url or title:
                    citations.append({"title": title, "url": url})
    return citations


def _iter_openai_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for output_item in _get_value(response, "output", []) or []:
        if _get_value(output_item, "type") != "web_search_call":
            continue
        action = _get_value(output_item, "action", None)
        for source in _get_value(action, "sources", []) or []:
            url = str(_get_value(source, "url", "") or "").strip()
            title = str(_get_value(source, "title", "") or "").strip()
            if url or title:
                sources.append({"title": title, "url": url})
    return sources


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for link in links:
        key = (link.get("title", ""), link.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def _format_openai_web_search_response(response: Any) -> str:
    text = str(_get_value(response, "output_text", "") or "").strip()
    lines: list[str] = []
    if text:
        lines.append(text)

    citations = _dedupe_links(_iter_openai_citations(response))
    if citations:
        lines.append("Citations:")
        for index, citation in enumerate(citations, start=1):
            lines.append(f"{index}.")
            if citation.get("title"):
                lines.append(f"   Title: {citation['title']}")
            if citation.get("url"):
                lines.append(f"   URL: {citation['url']}")

    sources = _dedupe_links(_iter_openai_sources(response))
    if sources:
        lines.append("Sources consulted:")
        for index, source in enumerate(sources, start=1):
            lines.append(f"{index}.")
            if source.get("title"):
                lines.append(f"   Title: {source['title']}")
            if source.get("url"):
                lines.append(f"   URL: {source['url']}")

    return "\n".join(lines).strip()


def fetch_web_search_context(query: str) -> str:
    """
    Use OpenAI Responses API web search and normalize the answer plus citations for prompts.
    """
    enabled = getattr(settings, "WEB_SEARCH_ENABLED", False)
    if not enabled:
        return "(Web search is disabled; proceed without verified external facts.)"

    q = (query or "").strip()
    if not q:
        return "(No search query could be built; proceed using discussion context only.)"

    api_key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        return "(OpenAI API key is not configured; proceed without verified external facts.)"

    model = (getattr(settings, "WEB_SEARCH_MODEL", "") or "gpt-5").strip()
    timeout = float(getattr(settings, "WEB_SEARCH_TIMEOUT_SEC", 15.0))
    try:
        client = OpenAI(api_key=api_key, timeout=timeout)
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            input=q,
        )
    except OpenAIError as exc:
        logger.warning("Web search request failed: %s", exc)
        return "(Web search failed; proceed without verified external facts.)"

    formatted = _format_openai_web_search_response(response)
    return formatted or "(Web search returned no usable snippets.)"

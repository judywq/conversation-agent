from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model

from backend.conversation.models import ConversationSession
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval

User = get_user_model()

SOURCE_SUCCESS = "success"
SOURCE_NO_RESULTS = "no-results"
SOURCE_SKIPPED = "skipped"
SOURCE_NOT_CONFIGURED = "not-configured"
SOURCE_FAILED = "failed"
SUPPORTED_SOURCES = {"web", "session", "memory", "knowledge"}


@dataclass(frozen=True)
class RetrievedItem:
    source: str
    excerpt: str
    title: str = ""
    source_uri: str = ""
    source_label: str = ""
    score: float = 0.0
    metadata: dict[str, Any] | None = None

    def as_trace_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "excerpt": self.excerpt,
            "source_uri": self.source_uri,
            "source_label": self.source_label,
            "score": self.score,
            "metadata": self.metadata or {},
        }


@dataclass(frozen=True)
class RetrievedContext:
    query: str
    requested_sources: list[str]
    source_statuses: dict[str, str]
    items: list[RetrievedItem]
    rendered_context: str
    error_message: str = ""


def map_retrieval_sources(retrieval_requirement: str | None) -> set[str]:
    raw = (retrieval_requirement or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if raw == "web_search":
        return {"web", "knowledge"}
    if raw == "memory":
        return {"memory", "session", "knowledge"}
    return set()


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", (text or "").casefold()) if len(token) >= 2]


def _excerpt(text: str, *, max_chars: int = 360) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "..."


def _render_context(items: list[RetrievedItem], source_statuses: dict[str, str]) -> str:
    if not items:
        if source_statuses == {"none": SOURCE_SKIPPED}:
            return "No retrieval requested. Continue using conversation context only."
        return (
            "No usable retrieved information was found. Continue using conversation context only; "
            "do not invent citations."
        )

    lines = ["Retrieved information:"]
    for index, item in enumerate(items, start=1):
        label = item.title or item.source_label or f"{item.source} source"
        lines.append(f"{index}. Source: {item.source}")
        lines.append(f"   Title: {label}")
        if item.source_uri:
            lines.append(f"   URI: {item.source_uri}")
        lines.append(f"   Excerpt: {item.excerpt}")
    return "\n".join(lines)


def retrieve(
    query: str,
    *,
    session: ConversationSession,
    user: User,
    sources: set[str],
    top_k: int = 5,
) -> RetrievedContext:
    requested_sources = sorted(sources)
    source_statuses: dict[str, str] = {}
    items: list[RetrievedItem] = []

    if not requested_sources:
        source_statuses["none"] = SOURCE_SKIPPED
        return RetrievedContext(
            query=query,
            requested_sources=[],
            source_statuses=source_statuses,
            items=[],
            rendered_context=_render_context([], source_statuses),
        )

    for source in requested_sources:
        if source not in SUPPORTED_SOURCES:
            source_statuses[source] = SOURCE_SKIPPED

    rendered_context = _render_context(items[:top_k], source_statuses)
    return RetrievedContext(
        query=query,
        requested_sources=requested_sources,
        source_statuses=source_statuses,
        items=items[:top_k],
        rendered_context=rendered_context,
    )


def persist_turn_retrieval(turn: TurnRecord, context: RetrievedContext) -> TurnRetrieval:
    return TurnRetrieval.objects.create(
        turn=turn,
        query=context.query,
        requested_sources=context.requested_sources,
        source_statuses=context.source_statuses,
        items=[item.as_trace_dict() for item in context.items],
        rendered_context=context.rendered_context,
        error_message=context.error_message,
    )

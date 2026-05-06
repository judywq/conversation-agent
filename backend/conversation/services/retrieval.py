from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from django.contrib.auth import get_user_model

from backend.conversation.models import ConversationSession
from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.services.web_search import fetch_web_search_context

User = get_user_model()
logger = logging.getLogger(__name__)

SOURCE_SUCCESS = "success"
SOURCE_NO_RESULTS = "no-results"
SOURCE_SKIPPED = "skipped"
SOURCE_NOT_CONFIGURED = "not-configured"
SOURCE_FAILED = "failed"
SUPPORTED_SOURCES = {"web", "session", "memory", "knowledge"}
_WEB_STATUS_PREFIX = "(Web search"


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
    source_messages: dict[str, str] = field(default_factory=dict)
    error_message: str = ""


def map_retrieval_sources(retrieval_requirement: str | None) -> set[str]:
    raw = (retrieval_requirement or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if raw == "web_search":
        return {"web", "knowledge"}
    if raw == "memory":
        return {"memory", "session", "knowledge"}
    if raw and raw != "none":
        return {raw}
    return set()


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", (text or "").casefold()) if len(token) >= 2]


def _excerpt(text: str, *, max_chars: int = 360) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "..."


def _render_context(
    items: list[RetrievedItem],
    source_statuses: dict[str, str],
    *,
    source_messages: dict[str, str] | None = None,
) -> str:
    if not items:
        if source_statuses == {"none": SOURCE_SKIPPED}:
            return "No retrieval requested. Continue using conversation context only."
        messages = [message for message in (source_messages or {}).values() if message]
        if messages:
            return "\n".join(
                [
                    *messages,
                    "Continue using conversation context only; do not invent citations.",
                ],
            )
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


def _score_text(query_terms: list[str], *parts: str) -> float:
    haystack = " ".join(parts).casefold()
    return float(sum(1 for term in query_terms if term in haystack))


def _retrieve_memory() -> tuple[list[RetrievedItem], str]:
    return [], SOURCE_NOT_CONFIGURED


def _retrieve_web(query: str) -> tuple[list[RetrievedItem], str, str]:
    q = (query or "").strip()
    if not q:
        return [], SOURCE_SKIPPED, "(No search query could be built; proceed using discussion context only.)"

    rendered = (fetch_web_search_context(q) or "").strip()
    if not rendered:
        return [], SOURCE_NO_RESULTS, "(Web search returned empty content.)"

    if (rendered.startswith(_WEB_STATUS_PREFIX) or rendered.startswith("(No search query")) and rendered.endswith(")"):
        lowered = rendered.casefold()
        if "disabled" in lowered or "not configured" in lowered:
            return [], SOURCE_SKIPPED, rendered
        if "no search query could be built" in lowered:
            return [], SOURCE_SKIPPED, rendered
        if "failed" in lowered:
            return [], SOURCE_FAILED, rendered
        if "empty content" in lowered or "no usable snippets" in lowered:
            return [], SOURCE_NO_RESULTS, rendered
        return [], SOURCE_NO_RESULTS, rendered

    return [
        RetrievedItem(
            source="web",
            title="Web search results",
            excerpt=rendered,
            source_label="Web search",
            score=1000.0,
            metadata={"search_query": q},
        ),
    ], SOURCE_SUCCESS, ""


def _retrieve_session(
    session: ConversationSession,
    query: str,
    *,
    top_k: int,
) -> tuple[list[RetrievedItem], str]:
    terms = _tokenize(query)
    if not terms:
        return [], SOURCE_NO_RESULTS

    recent_indexes = list(
        session.turns.order_by("-turn_index")
        .values_list("turn_index", flat=True)
        .distinct()[:3],
    )
    candidates = []
    for turn in session.turns.exclude(turn_index__in=recent_indexes).order_by("-turn_index", "-subturn_index"):
        score = _score_text(terms, turn.utterance)
        if score <= 0:
            continue
        candidates.append((score + (turn.turn_index / 1000.0), turn))

    if not candidates:
        return [], SOURCE_NO_RESULTS

    items = [
        RetrievedItem(
            source="session",
            title=f"Conversation turn {turn.turn_index}",
            excerpt=_excerpt(turn.utterance),
            score=score,
            metadata={
                "turn_id": turn.id,
                "turn_index": turn.turn_index,
                "subturn_index": turn.subturn_index,
                "speaker": turn.speaker,
                "speaker_type": turn.speaker_type,
            },
        )
        for score, turn in sorted(candidates, key=lambda x: x[0], reverse=True)[:top_k]
    ]
    return items, SOURCE_SUCCESS


def _retrieve_knowledge(query: str, *, top_k: int) -> tuple[list[RetrievedItem], str]:
    terms = _tokenize(query)
    if not terms:
        return [], SOURCE_NO_RESULTS

    candidates = []
    for snippet in KnowledgeSnippet.objects.filter(is_active=True):
        score = _score_text(terms, snippet.content, snippet.source_label)
        title_score = _score_text(terms, snippet.title) * 2.0
        total = score + title_score
        if total <= 0:
            continue
        candidates.append((total, snippet))

    if not candidates:
        return [], SOURCE_NO_RESULTS

    items = [
        RetrievedItem(
            source="knowledge",
            title=snippet.title,
            excerpt=_excerpt(snippet.content),
            source_uri=snippet.source_uri,
            source_label=snippet.source_label,
            score=score,
            metadata={"knowledge_snippet_id": snippet.id, "metadata": snippet.metadata},
        )
        for score, snippet in sorted(candidates, key=lambda x: x[0], reverse=True)[:top_k]
    ]
    return items, SOURCE_SUCCESS


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
    source_messages: dict[str, str] = {}
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
            continue
        if source == "web":
            found, status, message = _retrieve_web(query)
            if message:
                source_messages[source] = message
        elif source == "memory":
            found, status = _retrieve_memory()
        elif source == "session":
            if session.user_id != getattr(user, "id", None):
                found, status = [], SOURCE_SKIPPED
            else:
                found, status = _retrieve_session(session, query, top_k=top_k)
        elif source == "knowledge":
            found, status = _retrieve_knowledge(query, top_k=top_k)
        else:
            found, status = [], SOURCE_SKIPPED
        source_statuses[source] = status
        items.extend(found)

    ranked_items = sorted(items, key=lambda item: item.score, reverse=True)[:top_k]
    rendered_context = _render_context(
        ranked_items,
        source_statuses,
        source_messages=source_messages,
    )
    return RetrievedContext(
        query=query,
        requested_sources=requested_sources,
        source_statuses=source_statuses,
        items=ranked_items,
        rendered_context=rendered_context,
        source_messages=source_messages,
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


def persist_turn_retrieval_safely(turn: TurnRecord, context: RetrievedContext) -> TurnRetrieval | None:
    try:
        return persist_turn_retrieval(turn, context)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval trace persistence failed for turn %s: %s", turn.id, exc)
        return None

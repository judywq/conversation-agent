from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from pgvector.django import CosineDistance

from backend.conversation.models import ConversationSession
from backend.conversation.models import KnowledgeSnippet
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.web_search import fetch_web_search_context

User = get_user_model()
logger = logging.getLogger(__name__)

SOURCE_SUCCESS = "success"
SOURCE_NO_RESULTS = "no-results"
SOURCE_SKIPPED = "skipped"
SOURCE_NOT_CONFIGURED = "not-configured"
SOURCE_FAILED = "failed"
SUPPORTED_SOURCES = {"web", "session", "memory", "knowledge", "exemplar"}
_WEB_STATUS_PREFIX = "(Web search"
_EXEMPLAR_LABEL_MATCH_FALLBACK_SCORE = 0.1


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


@dataclass
class _KnowledgeCandidate:
    snippet: KnowledgeSnippet
    keyword_score: float | None = None
    keyword_rank: int | None = None
    vector_similarity: float | None = None
    vector_rank: int | None = None
    embedding_model: str = ""

    @property
    def retrieval_channels(self) -> list[str]:
        channels = []
        if self.keyword_rank is not None:
            channels.append("keyword")
        if self.vector_rank is not None:
            channels.append("vector")
        return channels

    def rerank_score(self) -> float:
        rrf_k = float(getattr(settings, "HYBRID_RRF_K", 60))
        keyword_weight = float(getattr(settings, "HYBRID_KEYWORD_WEIGHT", 1.0))
        vector_weight = float(getattr(settings, "HYBRID_VECTOR_WEIGHT", 1.0))
        score = 0.0
        if self.keyword_rank is not None:
            score += keyword_weight / (rrf_k + self.keyword_rank)
        if self.vector_rank is not None:
            score += vector_weight / (rrf_k + self.vector_rank)
        return score

    def global_score(self) -> float:
        score = (self.keyword_score or 0.0) + max(self.vector_similarity or 0.0, 0.0)
        return score or self.rerank_score()


def map_retrieval_sources(retrieval_requirement: str | None) -> set[str]:
    raw = (retrieval_requirement or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if raw == "web_search":
        return {"web", "knowledge"}
    if raw == "memory":
        return {"memory", "session", "knowledge"}
    if raw in {"exemplar", "speech_act_exemplar"}:
        return {"exemplar"}
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
        if "exemplar" in source_statuses:
            return "\n".join(
                [
                    *messages,
                    "No usable Speech Act examples were found.",
                    "Continue using conversation context only; do not invent citations.",
                ],
            )
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
    if any(item.source == "exemplar" for item in items):
        lines.extend(
            [
                "Speech Act examples are style and intent guidance only.",
                "Do not treat them as factual citations or source claims.",
            ],
        )
    for index, item in enumerate(items, start=1):
        label = item.title or item.source_label or f"{item.source} source"
        lines.append(f"{index}. Source: {item.source}")
        lines.append(f"   Title: {label}")
        if item.source_uri:
            lines.append(f"   URI: {item.source_uri}")
        if item.source == "exemplar":
            metadata = item.metadata if isinstance(item.metadata, dict) else {}
            speech_act_type = str(metadata.get("SA_type") or "").strip()
            speech_act_subtype = str(metadata.get("subtype") or "").strip()
            speech_act = "/".join(
                part for part in (speech_act_type, speech_act_subtype) if part
            )
            source_file = str(
                metadata.get("file_name") or item.source_label or "",
            ).strip()
            previous_sentence = str(metadata.get("previous_sentence") or "").strip()
            next_sentence = str(metadata.get("next_sentence") or "").strip()
            snippet_id = metadata.get("knowledge_snippet_id")
            if speech_act:
                lines.append(f"   Speech Act: {speech_act}")
            if source_file:
                lines.append(f"   Source file: {source_file}")
            if previous_sentence:
                lines.append(f"   Previous: {previous_sentence}")
            if next_sentence:
                lines.append(f"   Next: {next_sentence}")
            if snippet_id not in (None, ""):
                lines.append(f"   Snippet ID: {snippet_id}")
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


def _normal_knowledge_snippets() -> Any:
    return KnowledgeSnippet.objects.filter(is_active=True).filter(
        Q(metadata__kind__isnull=True) | ~Q(metadata__kind="speech_act_exemplar"),
    )


def _keyword_knowledge_candidates(query: str, *, candidate_count: int) -> list[_KnowledgeCandidate]:
    terms = _tokenize(query)
    if not terms or candidate_count <= 0:
        return []

    scored_candidates = []
    for snippet in _normal_knowledge_snippets():
        score = _score_text(terms, snippet.content, snippet.source_label)
        title_score = _score_text(terms, snippet.title) * 2.0
        total = score + title_score
        if total <= 0:
            continue
        scored_candidates.append((total, snippet.id, snippet))

    ranked = sorted(scored_candidates, key=lambda x: (-x[0], x[1]))[:candidate_count]
    return [
        _KnowledgeCandidate(snippet=snippet, keyword_score=score, keyword_rank=rank)
        for rank, (score, _snippet_id, snippet) in enumerate(ranked, start=1)
    ]


def _expected_embedding_model() -> str:
    provider = str(getattr(settings, "EMBEDDING_PROVIDER", "openai")).strip().casefold()
    if provider == "fake":
        return "fake"
    return str(getattr(settings, "EMBEDDING_MODEL", ""))


def _expected_embedding_dimensions() -> int:
    return int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))


def _vector_knowledge_candidates(query: str, *, candidate_count: int) -> tuple[list[_KnowledgeCandidate], str]:
    if not getattr(settings, "VECTOR_RECALL_ENABLED", True) or candidate_count <= 0:
        return [], SOURCE_NO_RESULTS

    try:
        snippets = _normal_knowledge_snippets().filter(
            embedding__isnull=False,
            embedding_model=_expected_embedding_model(),
            embedding_dimensions=_expected_embedding_dimensions(),
        )
        if not snippets.exists():
            return [], SOURCE_NO_RESULTS
        result = generate_embedding(query)
        ranked = snippets.annotate(
            distance=CosineDistance("embedding", result.vector),
        ).order_by("distance", "id")[:candidate_count]
        candidates = []
        for rank, snippet in enumerate(ranked, start=1):
            distance = getattr(snippet, "distance", None)
            if distance is None:
                continue
            candidates.append(
                _KnowledgeCandidate(
                    snippet=snippet,
                    vector_similarity=1.0 - float(distance),
                    vector_rank=rank,
                    embedding_model=snippet.embedding_model or result.model,
                ),
            )
        return candidates, SOURCE_SUCCESS
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector knowledge recall failed; falling back to keyword-only: %s", exc)
        return [], SOURCE_FAILED


def _merge_knowledge_candidates(
    keyword_candidates: list[_KnowledgeCandidate],
    vector_candidates: list[_KnowledgeCandidate],
) -> list[_KnowledgeCandidate]:
    merged: dict[int, _KnowledgeCandidate] = {}
    for candidate in [*keyword_candidates, *vector_candidates]:
        snippet_id = candidate.snippet.id
        existing = merged.get(snippet_id)
        if existing is None:
            merged[snippet_id] = candidate
            continue
        if candidate.keyword_score is not None:
            existing.keyword_score = candidate.keyword_score
            existing.keyword_rank = candidate.keyword_rank
        if candidate.vector_similarity is not None:
            existing.vector_similarity = candidate.vector_similarity
            existing.vector_rank = candidate.vector_rank
            existing.embedding_model = candidate.embedding_model
    return list(merged.values())


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
    if not _tokenize(query):
        return [], SOURCE_NO_RESULTS

    keyword_candidate_count = int(getattr(settings, "HYBRID_KEYWORD_CANDIDATES", 20))
    vector_candidate_count = int(getattr(settings, "HYBRID_VECTOR_CANDIDATES", 20))
    keyword_candidates = _keyword_knowledge_candidates(
        query,
        candidate_count=keyword_candidate_count,
    )
    vector_candidates, vector_status = _vector_knowledge_candidates(
        query,
        candidate_count=vector_candidate_count,
    )
    candidates = _merge_knowledge_candidates(keyword_candidates, vector_candidates)

    if not candidates:
        if vector_status == SOURCE_FAILED:
            return [], SOURCE_FAILED
        return [], SOURCE_NO_RESULTS

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate.rerank_score(), candidate.snippet.id),
    )
    items = []
    for candidate in ranked_candidates[:top_k]:
        snippet = candidate.snippet
        rerank_score = candidate.rerank_score()
        global_score = candidate.global_score()
        items.append(
            RetrievedItem(
                source="knowledge",
                title=snippet.title,
                excerpt=_excerpt(snippet.content),
                source_uri=snippet.source_uri,
                source_label=snippet.source_label,
                score=global_score,
                metadata={
                    "knowledge_snippet_id": snippet.id,
                    "metadata": snippet.metadata,
                    "retrieval_channels": candidate.retrieval_channels,
                    "keyword_score": candidate.keyword_score,
                    "keyword_rank": candidate.keyword_rank,
                    "vector_similarity": candidate.vector_similarity,
                    "vector_rank": candidate.vector_rank,
                    "rerank_score": rerank_score,
                    "global_score": global_score,
                    "embedding_model": candidate.embedding_model,
                },
            ),
        )
    return items, SOURCE_SUCCESS


def _retrieve_exemplar(
    query: str,
    *,
    top_k: int,
    speech_act_type: str = "",
    speech_act_subtype: str = "",
) -> tuple[list[RetrievedItem], str]:
    requested_type = str(speech_act_type or "").strip().upper()
    requested_subtype = str(speech_act_subtype or "").strip().lower()
    has_label_filter = bool(requested_type or requested_subtype)

    snippets = KnowledgeSnippet.objects.filter(
        is_active=True,
        metadata__kind="speech_act_exemplar",
    ).order_by("id")
    if requested_type:
        snippets = snippets.filter(metadata__SA_type=requested_type)
    if requested_subtype:
        snippets = snippets.filter(metadata__subtype=requested_subtype)

    snippets = list(snippets)
    if not snippets:
        return [], SOURCE_NO_RESULTS

    terms = _tokenize(query)
    if not terms and not has_label_filter:
        return [], SOURCE_NO_RESULTS

    candidates: list[tuple[float, int, KnowledgeSnippet]] = []
    for snippet in snippets:
        raw_metadata = snippet.metadata if isinstance(snippet.metadata, dict) else {}
        previous_sentence = str(raw_metadata.get("previous_sentence") or "")
        next_sentence = str(raw_metadata.get("next_sentence") or "")
        score = _score_text(
            terms,
            snippet.content,
            snippet.title,
            snippet.source_label,
            previous_sentence,
            next_sentence,
        )
        if score <= 0:
            if not has_label_filter:
                continue
            score = _EXEMPLAR_LABEL_MATCH_FALLBACK_SCORE
        candidates.append((score, snippet.id, snippet))

    if not candidates:
        return [], SOURCE_NO_RESULTS

    items: list[RetrievedItem] = []
    ranked_candidates = sorted(candidates, key=lambda x: (-x[0], x[1]))[:top_k]
    for score, _snippet_id, snippet in ranked_candidates:
        raw_metadata = snippet.metadata if isinstance(snippet.metadata, dict) else {}
        items.append(
            RetrievedItem(
                source="exemplar",
                title=snippet.title,
                excerpt=_excerpt(snippet.content),
                source_uri=snippet.source_uri,
                source_label=snippet.source_label,
                score=score,
                metadata={
                    "knowledge_snippet_id": snippet.id,
                    "kind": raw_metadata.get("kind", ""),
                    "SA_type": raw_metadata.get("SA_type", ""),
                    "subtype": raw_metadata.get("subtype", ""),
                    "file_name": raw_metadata.get("file_name", ""),
                    "previous_sentence": raw_metadata.get("previous_sentence", ""),
                    "next_sentence": raw_metadata.get("next_sentence", ""),
                    "annotation_source": raw_metadata.get("annotation_source", ""),
                    "import_batch": raw_metadata.get("import_batch", ""),
                    "import_key": raw_metadata.get("import_key", ""),
                    "row_number": raw_metadata.get("row_number"),
                    "metadata": raw_metadata,
                },
            ),
        )
    return items, SOURCE_SUCCESS


def retrieve(  # noqa: C901, PLR0913
    query: str,
    *,
    session: ConversationSession,
    user: User,
    sources: set[str],
    top_k: int = 5,
    speech_act_type: str = "",
    speech_act_subtype: str = "",
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
        elif source == "exemplar":
            found, status = _retrieve_exemplar(
                query,
                top_k=top_k,
                speech_act_type=speech_act_type,
                speech_act_subtype=speech_act_subtype,
            )
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

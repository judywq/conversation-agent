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
from backend.conversation.models import Exemplar
from backend.conversation.models import SessionNewsChunk
from backend.conversation.models import TurnRecord
from backend.conversation.models import TurnRetrieval
from backend.conversation.models import UserMemory
from backend.conversation.services.embeddings import build_user_memory_embedding_text
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.speaker_memories import langmem_enabled
from backend.conversation.services.speaker_memories import search_user_memories
from backend.conversation.services.web_search import fetch_web_search_context

User = get_user_model()
logger = logging.getLogger(__name__)

SOURCE_SUCCESS = "success"
SOURCE_NO_RESULTS = "no-results"
SOURCE_SKIPPED = "skipped"
SOURCE_FAILED = "failed"
SUPPORTED_SOURCES = {"web", "session", "memory", "knowledge", "exemplar", "news"}
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
    exemplar: Exemplar
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


@dataclass
class _NewsChunkCandidate:
    chunk: SessionNewsChunk
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


@dataclass
class _MemoryCandidate:
    memory: UserMemory
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
        return {"web"}
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
            exemplar_id = metadata.get("exemplar_id")
            if speech_act:
                lines.append(f"   Speech Act: {speech_act}")
            if source_file:
                lines.append(f"   Source file: {source_file}")
            if previous_sentence:
                lines.append(f"   Previous: {previous_sentence}")
            if next_sentence:
                lines.append(f"   Next: {next_sentence}")
            if exemplar_id not in (None, ""):
                lines.append(f"   Exemplar ID: {exemplar_id}")
        lines.append(f"   Excerpt: {item.excerpt}")
    return "\n".join(lines)


def _score_text(query_terms: list[str], *parts: str) -> float:
    haystack = " ".join(parts).casefold()
    return float(sum(1 for term in query_terms if term in haystack))


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
    return Exemplar.objects.filter(is_active=True).filter(
        Q(metadata__kind__isnull=True) | ~Q(metadata__kind="speech_act_exemplar"),
    )


def _active_user_memories(user: User) -> Any:
    return UserMemory.objects.filter(user=user, is_active=True)


def _speech_act_exemplar_snippets(
    *,
    speech_act_type: str = "",
    speech_act_subtype: str = "",
) -> Any:
    snippets = Exemplar.objects.filter(
        is_active=True,
        metadata__kind="speech_act_exemplar",
    )
    if speech_act_type:
        snippets = snippets.filter(metadata__SA_type=speech_act_type)
    if speech_act_subtype:
        snippets = snippets.filter(metadata__subtype=speech_act_subtype)
    return snippets


def _keyword_candidates(
    query: str,
    snippets: Any,
    *,
    candidate_count: int,
    include_exemplar_context: bool = False,
) -> list[_KnowledgeCandidate]:
    terms = _tokenize(query)
    if not terms or candidate_count <= 0:
        return []

    scored_candidates = []
    for snippet in snippets:
        parts = [snippet.content, snippet.source_label, snippet.source_uri]
        if include_exemplar_context:
            raw_metadata = snippet.metadata if isinstance(snippet.metadata, dict) else {}
            parts.extend(
                [
                    snippet.title,
                    str(raw_metadata.get("previous_sentence") or ""),
                    str(raw_metadata.get("next_sentence") or ""),
                ],
            )
        score = _score_text(terms, *parts)
        title_score = _score_text(terms, snippet.title) * 2.0
        total = score + title_score
        if total <= 0:
            continue
        scored_candidates.append((total, snippet.id, snippet))

    ranked = sorted(scored_candidates, key=lambda x: (-x[0], x[1]))[:candidate_count]
    return [
        _KnowledgeCandidate(exemplar=snippet, keyword_score=score, keyword_rank=rank)
        for rank, (score, _snippet_id, snippet) in enumerate(ranked, start=1)
    ]


def _keyword_knowledge_candidates(query: str, *, candidate_count: int) -> list[_KnowledgeCandidate]:
    return _keyword_candidates(
        query,
        _normal_knowledge_snippets(),
        candidate_count=candidate_count,
    )


def _keyword_memory_candidates(
    query: str,
    memories: Any,
    *,
    candidate_count: int,
) -> list[_MemoryCandidate]:
    terms = _tokenize(query)
    if not terms or candidate_count <= 0:
        return []

    scored_candidates = []
    for memory in memories:
        score = _score_text(
            terms,
            memory.content,
            memory.memory_type,
            memory.source_label,
            memory.source_uri,
            build_user_memory_embedding_text(memory),
        )
        if score <= 0:
            continue
        scored_candidates.append((score, memory.id, memory))

    ranked = sorted(scored_candidates, key=lambda x: (-x[0], x[1]))[:candidate_count]
    return [
        _MemoryCandidate(memory=memory, keyword_score=score, keyword_rank=rank)
        for rank, (score, _memory_id, memory) in enumerate(ranked, start=1)
    ]


def _expected_embedding_model() -> str:
    provider = str(getattr(settings, "EMBEDDING_PROVIDER", "openai")).strip().casefold()
    if provider == "fake":
        return "fake"
    return str(getattr(settings, "EMBEDDING_MODEL", ""))


def _expected_embedding_dimensions() -> int:
    return int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))


def _vector_candidates(
    query: str,
    snippets: Any,
    *,
    candidate_count: int,
    log_label: str,
) -> tuple[list[_KnowledgeCandidate], str]:
    if not getattr(settings, "VECTOR_RECALL_ENABLED", True) or candidate_count <= 0:
        return [], SOURCE_SKIPPED

    try:
        snippets = snippets.filter(
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
                    exemplar=snippet,
                    vector_similarity=1.0 - float(distance),
                    vector_rank=rank,
                    embedding_model=snippet.embedding_model or result.model,
                ),
            )
        return candidates, SOURCE_SUCCESS
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector %s recall failed; falling back to keyword-only: %s", log_label, exc)
        return [], SOURCE_FAILED


def _vector_knowledge_candidates(query: str, *, candidate_count: int) -> tuple[list[_KnowledgeCandidate], str]:
    return _vector_candidates(
        query,
        _normal_knowledge_snippets(),
        candidate_count=candidate_count,
        log_label="knowledge",
    )


def _vector_memory_candidates(
    query: str,
    memories: Any,
    *,
    candidate_count: int,
) -> tuple[list[_MemoryCandidate], str]:
    if not getattr(settings, "VECTOR_RECALL_ENABLED", True) or candidate_count <= 0:
        return [], SOURCE_SKIPPED

    try:
        memories = memories.filter(
            embedding__isnull=False,
            embedding_model=_expected_embedding_model(),
            embedding_dimensions=_expected_embedding_dimensions(),
        )
        if not memories.exists():
            return [], SOURCE_NO_RESULTS
        result = generate_embedding(query)
        ranked = memories.annotate(
            distance=CosineDistance("embedding", result.vector),
        ).order_by("distance", "id")[:candidate_count]
        candidates = []
        for rank, memory in enumerate(ranked, start=1):
            distance = getattr(memory, "distance", None)
            if distance is None:
                continue
            candidates.append(
                _MemoryCandidate(
                    memory=memory,
                    vector_similarity=1.0 - float(distance),
                    vector_rank=rank,
                    embedding_model=memory.embedding_model or result.model,
                ),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Vector memory recall failed; falling back to keyword-only: %s",
            exc,
        )
        return [], SOURCE_FAILED
    else:
        return candidates, SOURCE_SUCCESS


def _merge_candidates(
    keyword_candidates: list[_KnowledgeCandidate],
    vector_candidates: list[_KnowledgeCandidate],
) -> list[_KnowledgeCandidate]:
    merged: dict[int, _KnowledgeCandidate] = {}
    for candidate in [*keyword_candidates, *vector_candidates]:
        exemplar_id = candidate.exemplar.id
        existing = merged.get(exemplar_id)
        if existing is None:
            merged[exemplar_id] = candidate
            continue
        if candidate.keyword_score is not None:
            existing.keyword_score = candidate.keyword_score
            existing.keyword_rank = candidate.keyword_rank
        if candidate.vector_similarity is not None:
            existing.vector_similarity = candidate.vector_similarity
            existing.vector_rank = candidate.vector_rank
            existing.embedding_model = candidate.embedding_model
    return list(merged.values())


def _merge_knowledge_candidates(
    keyword_candidates: list[_KnowledgeCandidate],
    vector_candidates: list[_KnowledgeCandidate],
) -> list[_KnowledgeCandidate]:
    return _merge_candidates(keyword_candidates, vector_candidates)


def _session_news_chunks(session: ConversationSession) -> Any:
    article_ids = session.discussion_article_ids or []
    queryset = SessionNewsChunk.objects.filter(session=session)
    if article_ids:
        queryset = queryset.filter(news_article_id__in=article_ids)
    else:
        queryset = queryset.filter(news_article__isnull=True)
    return queryset.select_related("news_article")


def _keyword_news_candidates(
    query: str,
    chunks: Any,
    *,
    candidate_count: int,
) -> list[_NewsChunkCandidate]:
    terms = _tokenize(query)
    if not terms or candidate_count <= 0:
        return []

    scored_candidates = []
    for chunk in chunks:
        article = chunk.news_article
        score = _score_text(
            terms,
            chunk.content,
            article.title if article else chunk.source_title,
            article.url if article else chunk.source_uri,
        )
        if score <= 0:
            continue
        scored_candidates.append((score, chunk.id, chunk))

    ranked = sorted(scored_candidates, key=lambda x: (-x[0], x[1]))[:candidate_count]
    return [
        _NewsChunkCandidate(chunk=chunk, keyword_score=score, keyword_rank=rank)
        for rank, (score, _chunk_id, chunk) in enumerate(ranked, start=1)
    ]


def _vector_news_candidates(
    query: str,
    chunks: Any,
    *,
    candidate_count: int,
) -> tuple[list[_NewsChunkCandidate], str]:
    if not getattr(settings, "VECTOR_RECALL_ENABLED", True) or candidate_count <= 0:
        return [], SOURCE_SKIPPED

    try:
        chunks = chunks.filter(
            embedding__isnull=False,
            embedding_model=_expected_embedding_model(),
            embedding_dimensions=_expected_embedding_dimensions(),
        )
        if not chunks.exists():
            return [], SOURCE_NO_RESULTS
        result = generate_embedding(query)
        ranked = chunks.annotate(
            distance=CosineDistance("embedding", result.vector),
        ).order_by("distance", "id")[:candidate_count]
        candidates = []
        for rank, chunk in enumerate(ranked, start=1):
            distance = getattr(chunk, "distance", None)
            if distance is None:
                continue
            candidates.append(
                _NewsChunkCandidate(
                    chunk=chunk,
                    vector_similarity=1.0 - float(distance),
                    vector_rank=rank,
                    embedding_model=chunk.embedding_model or result.model,
                ),
            )
        return candidates, SOURCE_SUCCESS
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector news recall failed; falling back to keyword-only: %s", exc)
        return [], SOURCE_FAILED


def _merge_news_candidates(
    keyword_candidates: list[_NewsChunkCandidate],
    vector_candidates: list[_NewsChunkCandidate],
) -> list[_NewsChunkCandidate]:
    merged: dict[int, _NewsChunkCandidate] = {}
    for candidate in [*keyword_candidates, *vector_candidates]:
        chunk_id = candidate.chunk.id
        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = candidate
            continue
        if candidate.keyword_score is not None:
            existing.keyword_score = candidate.keyword_score
            existing.keyword_rank = candidate.keyword_rank
        if candidate.vector_similarity is not None:
            existing.vector_similarity = candidate.vector_similarity
            existing.vector_rank = candidate.vector_rank
            existing.embedding_model = candidate.embedding_model
    return list(merged.values())


def _merge_memory_candidates(
    keyword_candidates: list[_MemoryCandidate],
    vector_candidates: list[_MemoryCandidate],
) -> list[_MemoryCandidate]:
    merged: dict[int, _MemoryCandidate] = {}
    for candidate in [*keyword_candidates, *vector_candidates]:
        memory_id = candidate.memory.id
        existing = merged.get(memory_id)
        if existing is None:
            merged[memory_id] = candidate
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




def _retrieve_langmem(
    query: str,
    *,
    user: User,
    agent_slug: str | None = None,
    top_k: int,
) -> tuple[list[RetrievedItem], str]:
    if not langmem_enabled():
        return [], SOURCE_SKIPPED
    if not _tokenize(query):
        return [], SOURCE_NO_RESULTS
    try:
        hits = search_user_memories(user, query, agent_slug=agent_slug, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangMem retrieval failed: %s", exc)
        return [], SOURCE_FAILED
    if not hits:
        return [], SOURCE_NO_RESULTS
    items: list[RetrievedItem] = []
    for row, score, namespace in hits:
        items.append(
            RetrievedItem(
                source="memory",
                title=row.memory_type,
                excerpt=_excerpt(row.content),
                source_label=row.source_label or "langmem",
                score=float(score),
                metadata={
                    "langmem": True,
                    "namespace": "/".join(namespace),
                    "memory_type": row.memory_type,
                    "confidence": row.confidence,
                    "speaker": row.speaker,
                    "metadata": row.metadata,
                },
            ),
        )
    return items, SOURCE_SUCCESS


def _merge_memory_items_langmem_first(
    langmem_items: list[RetrievedItem],
    legacy_items: list[RetrievedItem],
    *,
    top_k: int,
) -> list[RetrievedItem]:
    merged: list[RetrievedItem] = []
    seen: set[str] = set()
    for item in [*langmem_items, *legacy_items]:
        key = " ".join((item.title or "", item.excerpt or "").casefold().split())
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= top_k:
            break
    return merged


def _retrieve_combined_memory(
    query: str,
    *,
    user: User,
    agent_slug: str | None = None,
    top_k: int,
) -> tuple[list[RetrievedItem], str]:
    langmem_items, langmem_status = _retrieve_langmem(
        query,
        user=user,
        agent_slug=agent_slug,
        top_k=top_k,
    )
    legacy_enabled = getattr(settings, "USER_MEMORY_EXTRACTION_ENABLED", True)
    if not legacy_enabled:
        return langmem_items, langmem_status

    legacy_items, legacy_status = _retrieve_memory(query, user=user, top_k=top_k)
    merged = _merge_memory_items_langmem_first(langmem_items, legacy_items, top_k=top_k)
    if merged:
        return merged, SOURCE_SUCCESS
    if langmem_status == SOURCE_FAILED or legacy_status == SOURCE_FAILED:
        return [], SOURCE_FAILED
    if langmem_status == SOURCE_NO_RESULTS and legacy_status == SOURCE_NO_RESULTS:
        return [], SOURCE_NO_RESULTS
    return [], langmem_status if langmem_status != SOURCE_SKIPPED else legacy_status


def _retrieve_memory(
    query: str,
    *,
    user: User,
    top_k: int,
) -> tuple[list[RetrievedItem], str]:
    if not _tokenize(query):
        return [], SOURCE_NO_RESULTS

    memories = _active_user_memories(user)
    keyword_candidate_count = int(getattr(settings, "HYBRID_KEYWORD_CANDIDATES", 20))
    vector_candidate_count = int(getattr(settings, "HYBRID_VECTOR_CANDIDATES", 20))
    keyword_candidates = _keyword_memory_candidates(
        query,
        memories.order_by("id"),
        candidate_count=keyword_candidate_count,
    )
    vector_candidates, vector_status = _vector_memory_candidates(
        query,
        memories,
        candidate_count=vector_candidate_count,
    )
    candidates = _merge_memory_candidates(keyword_candidates, vector_candidates)

    if not candidates:
        if vector_status == SOURCE_FAILED:
            return [], SOURCE_FAILED
        return [], SOURCE_NO_RESULTS

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate.rerank_score(), candidate.memory.id),
    )
    items = []
    for candidate in ranked_candidates[:top_k]:
        memory = candidate.memory
        rerank_score = candidate.rerank_score()
        global_score = candidate.global_score()
        items.append(
            RetrievedItem(
                source="memory",
                title=memory.memory_type,
                excerpt=_excerpt(memory.content),
                source_uri=memory.source_uri,
                source_label=memory.source_label,
                score=global_score,
                metadata={
                    "user_memory_id": memory.id,
                    "memory_type": memory.memory_type,
                    "confidence": memory.confidence,
                    "metadata": memory.metadata,
                    "retrieval_channels": candidate.retrieval_channels,
                    "vector_status": vector_status,
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


def _retrieve_news(
    session: ConversationSession,
    query: str,
    *,
    top_k: int,
) -> tuple[list[RetrievedItem], str]:
    chunks = _session_news_chunks(session)
    if not chunks.exists():
        return [], SOURCE_NO_RESULTS
    if not _tokenize(query):
        return [], SOURCE_NO_RESULTS

    keyword_candidate_count = int(getattr(settings, "HYBRID_KEYWORD_CANDIDATES", 20))
    vector_candidate_count = int(getattr(settings, "HYBRID_VECTOR_CANDIDATES", 20))
    keyword_candidates = _keyword_news_candidates(
        query,
        chunks.order_by("id"),
        candidate_count=keyword_candidate_count,
    )
    vector_candidates, vector_status = _vector_news_candidates(
        query,
        chunks,
        candidate_count=vector_candidate_count,
    )
    candidates = _merge_news_candidates(keyword_candidates, vector_candidates)

    if not candidates:
        if vector_status == SOURCE_FAILED:
            return [], SOURCE_FAILED
        return [], SOURCE_NO_RESULTS

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate.rerank_score(), candidate.chunk.id),
    )
    items = []
    for candidate in ranked_candidates[:top_k]:
        chunk = candidate.chunk
        article = chunk.news_article
        rerank_score = candidate.rerank_score()
        global_score = candidate.global_score()
        items.append(
            RetrievedItem(
                source="news",
                title=(
                    article.title
                    if article
                    else (chunk.source_title or f"News chunk {chunk.chunk_index}")
                ),
                excerpt=_excerpt(chunk.content),
                source_uri=article.url if article else chunk.source_uri,
                source_label=article.feed_title if article else chunk.source_title,
                score=global_score,
                metadata={
                    "session_news_chunk_id": chunk.id,
                    "news_article_id": chunk.news_article_id,
                    "chunk_index": chunk.chunk_index,
                    "retrieval_channels": candidate.retrieval_channels,
                    "vector_status": vector_status,
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
        key=lambda candidate: (-candidate.rerank_score(), candidate.exemplar.id),
    )
    items = []
    for candidate in ranked_candidates[:top_k]:
        exemplar = candidate.exemplar
        rerank_score = candidate.rerank_score()
        global_score = candidate.global_score()
        items.append(
            RetrievedItem(
                source="knowledge",
                title=exemplar.title,
                excerpt=_excerpt(exemplar.content),
                source_uri=exemplar.source_uri,
                source_label=exemplar.source_label,
                score=global_score,
                metadata={
                    "exemplar_id": exemplar.id,
                    "metadata": exemplar.metadata,
                    "retrieval_channels": candidate.retrieval_channels,
                    "vector_status": vector_status,
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

    snippets = _speech_act_exemplar_snippets(
        speech_act_type=requested_type,
        speech_act_subtype=requested_subtype,
    )
    if not snippets.exists():
        return [], SOURCE_NO_RESULTS

    terms = _tokenize(query)
    if not terms and not has_label_filter:
        return [], SOURCE_NO_RESULTS

    keyword_candidate_count = int(getattr(settings, "HYBRID_KEYWORD_CANDIDATES", 20))
    if keyword_candidate_count > 0:
        keyword_candidate_count = max(keyword_candidate_count, top_k)
    vector_candidate_count = int(getattr(settings, "HYBRID_VECTOR_CANDIDATES", 20))
    if vector_candidate_count > 0:
        vector_candidate_count = max(vector_candidate_count, top_k)
    keyword_candidates = _keyword_candidates(
        query,
        snippets.order_by("id"),
        candidate_count=keyword_candidate_count,
        include_exemplar_context=True,
    )
    if terms:
        vector_candidates, vector_status = _vector_candidates(
            query,
            snippets,
            candidate_count=vector_candidate_count,
            log_label="speech act exemplar",
        )
    else:
        vector_candidates, vector_status = [], SOURCE_NO_RESULTS
    candidates = _merge_candidates(keyword_candidates, vector_candidates)
    if has_label_filter:
        candidate_ids = {candidate.exemplar.id for candidate in candidates}
        for snippet in snippets.order_by("id"):
            if snippet.id in candidate_ids:
                continue
            candidates.append(
                _KnowledgeCandidate(
                    exemplar=snippet,
                    keyword_score=_EXEMPLAR_LABEL_MATCH_FALLBACK_SCORE,
                    keyword_rank=None,
                ),
            )
    if not candidates:
        if vector_status == SOURCE_FAILED:
            return [], SOURCE_FAILED
        return [], SOURCE_NO_RESULTS

    items: list[RetrievedItem] = []
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.rerank_score(),
            -candidate.global_score(),
            candidate.exemplar.id,
        ),
    )[:top_k]
    for candidate in ranked_candidates:
        exemplar = candidate.exemplar
        raw_metadata = exemplar.metadata if isinstance(exemplar.metadata, dict) else {}
        rerank_score = candidate.rerank_score()
        global_score = candidate.global_score()
        items.append(
            RetrievedItem(
                source="exemplar",
                title=exemplar.title,
                excerpt=_excerpt(exemplar.content),
                source_uri=exemplar.source_uri,
                source_label=exemplar.source_label,
                score=global_score,
                metadata={
                    "exemplar_id": exemplar.id,
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
                    "retrieval_channels": candidate.retrieval_channels or ["label_filter"],
                    "vector_status": vector_status,
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


def retrieve(  # noqa: C901, PLR0913
    query: str,
    *,
    session: ConversationSession,
    user: User,
    sources: set[str],
    top_k: int = 5,
    speech_act_type: str = "",
    speech_act_subtype: str = "",
    agent_slug: str | None = None,
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
            if session.user_id != getattr(user, "id", None):
                found, status = [], SOURCE_SKIPPED
            else:
                found, status = _retrieve_combined_memory(
                    query,
                    user=user,
                    agent_slug=agent_slug,
                    top_k=top_k,
                )
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
        elif source == "news":
            found, status = _retrieve_news(session, query, top_k=top_k)
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

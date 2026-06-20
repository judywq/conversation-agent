from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from backend.conversation.models import ConversationSession
from backend.conversation.models import SessionNewsChunk
from backend.conversation.services.embeddings import embedding_text_hash
from backend.conversation.services.embeddings import generate_embeddings
from backend.news.models import NewsArticle

logger = logging.getLogger(__name__)

CHUNK_WORDS = 600
CHUNK_OVERLAP_WORDS = 100


def _split_words(text: str) -> list[str]:
    return (text or "").split()


def chunk_article_text(text: str, *, chunk_words: int = CHUNK_WORDS, overlap_words: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = _split_words(text)
    if not words:
        return []
    if len(words) <= chunk_words:
        return [" ".join(words)]

    step = max(1, chunk_words - overlap_words)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        piece = words[start : start + chunk_words]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + chunk_words >= len(words):
            break
        start += step
    return chunks


def _article_body(article: NewsArticle) -> str:
    body = (article.full_text or "").strip()
    if body:
        return body
    return (article.summary or "").strip()


def build_session_news_chunks(
    session: ConversationSession,
    article_ids: list[int],
) -> list[SessionNewsChunk]:
    if not article_ids:
        SessionNewsChunk.objects.filter(session=session).delete()
        return []

    articles = list(
        NewsArticle.objects.filter(id__in=article_ids).order_by("id"),
    )
    SessionNewsChunk.objects.filter(session=session).delete()

    rows: list[SessionNewsChunk] = []
    for article in articles:
        for index, content in enumerate(chunk_article_text(_article_body(article))):
            rows.append(
                SessionNewsChunk(
                    session=session,
                    news_article=article,
                    chunk_index=index,
                    content=content,
                ),
            )

    if not rows:
        return []

    created = SessionNewsChunk.objects.bulk_create(rows)
    logger.info(
        "session_news_chunks_created session_id=%s article_count=%d chunk_count=%d",
        session.id,
        len(articles),
        len(created),
    )
    return created


def embed_session_news_chunks(chunks: list[SessionNewsChunk]) -> None:
    if not chunks:
        return

    texts = [chunk.content for chunk in chunks]
    batch_size = int(getattr(settings, "EMBEDDING_BATCH_SIZE", 32))
    now = timezone.now()

    for offset in range(0, len(texts), batch_size):
        batch_chunks = chunks[offset : offset + batch_size]
        batch_texts = texts[offset : offset + batch_size]
        results = generate_embeddings(batch_texts)
        for chunk, result in zip(batch_chunks, results, strict=True):
            chunk.embedding = result.vector
            chunk.embedding_model = result.model
            chunk.embedding_dimensions = result.dimensions
            chunk.embedding_text_hash = embedding_text_hash(chunk.content)
            chunk.embedding_updated_at = now

    SessionNewsChunk.objects.bulk_update(
        chunks,
        fields=[
            "embedding",
            "embedding_model",
            "embedding_dimensions",
            "embedding_text_hash",
            "embedding_updated_at",
        ],
    )


def materialize_session_news_knowledge(
    session: ConversationSession,
    article_ids: list[int],
) -> int:
    chunks = build_session_news_chunks(session, article_ids)
    embed_session_news_chunks(chunks)
    return len(chunks)


WEB_KNOWLEDGE_SOURCE_TITLE = "Web search"


def build_session_web_chunks(
    session: ConversationSession,
    web_context: str,
    *,
    source_title: str = WEB_KNOWLEDGE_SOURCE_TITLE,
) -> list[SessionNewsChunk]:
    text = (web_context or "").strip()
    SessionNewsChunk.objects.filter(session=session).delete()
    if not text:
        return []

    rows = [
        SessionNewsChunk(
            session=session,
            news_article=None,
            chunk_index=index,
            content=content,
            source_title=source_title,
        )
        for index, content in enumerate(chunk_article_text(text))
    ]
    if not rows:
        return []

    created = SessionNewsChunk.objects.bulk_create(rows)
    logger.info(
        "session_web_chunks_created session_id=%s chunk_count=%d",
        session.id,
        len(created),
    )
    return created


def materialize_session_web_knowledge(
    session: ConversationSession,
    web_context: str,
) -> int:
    chunks = build_session_web_chunks(session, web_context)
    embed_session_news_chunks(chunks)
    return len(chunks)

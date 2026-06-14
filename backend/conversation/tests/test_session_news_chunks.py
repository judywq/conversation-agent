import pytest
from django.utils import timezone

from backend.conversation.models import ConversationSession
from backend.conversation.models import SessionNewsChunk
from backend.conversation.services.session_news_chunks import chunk_article_text
from backend.conversation.services.session_news_chunks import materialize_session_news_knowledge
from backend.news.models import NewsArticle


@pytest.mark.django_db
def test_chunk_article_text_splits_long_body():
    words = [f"word{i}" for i in range(700)]
    chunks = chunk_article_text(" ".join(words), chunk_words=600, overlap_words=100)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


@pytest.mark.django_db
def test_materialize_session_news_knowledge_creates_chunks(user):
    article = NewsArticle.objects.create(
        miniflux_entry_id=601,
        miniflux_feed_id=1,
        feed_title="Feed",
        title="Article",
        summary="Summary",
        full_text=" ".join(f"fact{i}" for i in range(700)),
        url="https://example.com/article",
        normalized_url="https://example.com/article",
        published_at=timezone.now(),
    )
    session = ConversationSession.objects.create(user=user, topic="Topic")

    count = materialize_session_news_knowledge(session, [article.id])

    assert count >= 2
    assert SessionNewsChunk.objects.filter(session=session, news_article=article).count() == count
    assert all(chunk.embedding for chunk in SessionNewsChunk.objects.filter(session=session))

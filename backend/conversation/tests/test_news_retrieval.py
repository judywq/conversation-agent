import pytest
from django.utils import timezone

from backend.conversation.models import ConversationSession
from backend.conversation.models import SessionNewsChunk
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.retrieval import retrieve
from backend.news.models import NewsArticle
from backend.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_retrieve_news_returns_only_current_session_chunks(user):
    other_user = UserFactory()
    article = NewsArticle.objects.create(
        miniflux_entry_id=801,
        miniflux_feed_id=1,
        feed_title="Feed",
        title="Campus AI policy",
        summary="Summary",
        full_text="Students discuss whether AI tutors should replace teachers on campus.",
        url="https://example.com/ai",
        normalized_url="https://example.com/ai",
        published_at=timezone.now(),
    )
    session = ConversationSession.objects.create(
        user=user,
        topic="AI tutors",
        discussion_article_ids=[article.id],
    )
    other_session = ConversationSession.objects.create(
        user=other_user,
        topic="Other topic",
        discussion_article_ids=[article.id],
    )

    chunk = SessionNewsChunk.objects.create(
        session=session,
        news_article=article,
        chunk_index=0,
        content=article.full_text,
    )
    result = generate_embedding(chunk.content)
    chunk.embedding = result.vector
    chunk.embedding_model = result.model
    chunk.embedding_dimensions = result.dimensions
    chunk.embedding_text_hash = result.text_hash
    chunk.save()

    SessionNewsChunk.objects.create(
        session=other_session,
        news_article=article,
        chunk_index=0,
        content="Unrelated session chunk about sports.",
    )

    context = retrieve(
        "AI tutors on campus",
        session=session,
        user=user,
        sources={"news"},
        top_k=3,
    )

    assert context.items
    assert all(item.source == "news" for item in context.items)
    assert "AI tutors" in context.items[0].excerpt

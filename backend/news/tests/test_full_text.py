import pytest
from django.utils import timezone

from backend.news.full_text import fetch_and_store_full_text
from backend.news.miniflux import MinifluxRequestError
from backend.news.models import NewsArticle


class FakeMinifluxClient:
    def __init__(self, payloads=None, error_on=None):
        self.payloads = payloads or {}
        self.error_on = set(error_on or [])

    def fetch_entry_content(self, entry_id: int, *, update_content: bool = True) -> str:
        if entry_id in self.error_on:
            raise MinifluxRequestError("boom")
        return self.payloads.get(entry_id, "<p>Full article body from Miniflux.</p>")


@pytest.mark.django_db
def test_fetch_and_store_full_text_saves_plain_text():
    article = NewsArticle.objects.create(
        miniflux_entry_id=501,
        miniflux_feed_id=1,
        feed_title="Feed",
        title="AI tutors",
        summary="Short summary.",
        url="https://example.com/ai",
        normalized_url="https://example.com/ai",
        published_at=timezone.now(),
    )

    updated = fetch_and_store_full_text(
        [article],
        client=FakeMinifluxClient({501: "<p>Full article body from Miniflux.</p>"}),
    )

    article.refresh_from_db()
    assert updated[0].full_text == "Full article body from Miniflux."
    assert article.full_text == "Full article body from Miniflux."


@pytest.mark.django_db
def test_fetch_and_store_full_text_falls_back_to_summary_on_failure():
    article = NewsArticle.objects.create(
        miniflux_entry_id=502,
        miniflux_feed_id=1,
        feed_title="Feed",
        title="Campus policy",
        summary="Fallback summary text.",
        url="https://example.com/policy",
        normalized_url="https://example.com/policy",
        published_at=timezone.now(),
    )

    fetch_and_store_full_text([article], client=FakeMinifluxClient(error_on={502}))

    article.refresh_from_db()
    assert article.full_text == "Fallback summary text."

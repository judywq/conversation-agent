import pytest
from django.test import override_settings

from backend.conversation.services.web_search import _format_search_payload
from backend.conversation.services.web_search import build_web_search_query
from backend.conversation.services.web_search import fetch_web_search_context
from backend.conversation.services.web_search import wants_web_search


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("web_search", True),
        ("WEB_SEARCH", True),
        ("web search", True),
        ("web-search", True),
        ("memory", False),
        ("none", False),
        ("", False),
    ],
)
def test_wants_web_search(raw: str, expected: bool) -> None:
    assert wants_web_search(raw) is expected


def test_format_search_payload_includes_provenance_fields() -> None:
    out = _format_search_payload(
        {
            "results": [
                {
                    "title": "Annual climate outlook",
                    "author": "A. Ng",
                    "organization": "NOAA",
                    "url": "https://example.org/report",
                    "snippet": "Sea levels rose.",
                },
            ],
        },
    )
    assert "Title: Annual climate outlook" in out
    assert "Author: A. Ng" in out
    assert "Organization: NOAA" in out
    assert "URL: https://example.org/report" in out
    assert "Excerpt: Sea levels rose." in out


def test_build_web_search_query_includes_all_parts() -> None:
    q = build_web_search_query(
        topic="Climate change",
        content_requirement="Cite a recent policy example.",
        last_speaker_line="I think we need more data.",
    )
    assert "Topic: Climate change" in q
    assert "Facilitator instruction: Cite a recent policy example." in q
    assert "Latest turn: I think we need more data." in q
    assert q.index("Topic:") < q.index("Facilitator")
    assert q.index("Facilitator") < q.index("Latest turn:")


@override_settings(WEB_SEARCH_ENABLED=False, WEB_SEARCH_API_URL="https://example.com/search")
def test_fetch_respects_disabled() -> None:
    out = fetch_web_search_context("Topic: t\nFacilitator instruction: i\nLatest turn: l")
    assert "disabled" in out.lower() or "not configured" in out.lower()


@override_settings(WEB_SEARCH_ENABLED=True, WEB_SEARCH_API_URL="")
def test_fetch_respects_missing_url() -> None:
    out = fetch_web_search_context("any")
    assert "not configured" in out.lower() or "disabled" in out.lower()

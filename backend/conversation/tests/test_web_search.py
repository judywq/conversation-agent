import pytest
from django.test import override_settings
from types import SimpleNamespace
from unittest.mock import patch

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


@override_settings(WEB_SEARCH_ENABLED=False)
def test_fetch_respects_disabled() -> None:
    out = fetch_web_search_context("Topic: t\nFacilitator instruction: i\nLatest turn: l")
    assert "disabled" in out.lower()


@override_settings(WEB_SEARCH_ENABLED=True, OPENAI_API_KEY="")
def test_fetch_respects_missing_openai_key() -> None:
    out = fetch_web_search_context("any")
    assert "openai api key" in out.lower()


@override_settings(
    WEB_SEARCH_ENABLED=True,
    OPENAI_API_KEY="sk-test",
    WEB_SEARCH_MODEL="gpt-5",
    WEB_SEARCH_TIMEOUT_SEC=12.0,
)
def test_fetch_uses_openai_web_search_tool() -> None:
    response = SimpleNamespace(
        output_text="OpenAI supports web search through the Responses API.",
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        text="OpenAI supports web search through the Responses API.",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Web search",
                                url="https://platform.openai.com/docs/guides/tools-web-search",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    with patch("backend.conversation.services.web_search.OpenAI") as openai:
        openai.return_value.responses.create.return_value = response

        out = fetch_web_search_context("latest OpenAI web search API docs")

    openai.assert_called_once_with(api_key="sk-test", timeout=12.0)
    openai.return_value.responses.create.assert_called_once_with(
        model="gpt-5",
        tools=[{"type": "web_search"}],
        tool_choice="auto",
        include=["web_search_call.action.sources"],
        input="latest OpenAI web search API docs",
    )
    assert "OpenAI supports web search" in out
    assert "Title: Web search" in out
    assert "URL: https://platform.openai.com/docs/guides/tools-web-search" in out

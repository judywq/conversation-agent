# ruff: noqa: E501, EM101, PLR2004, S106, TRY003

import pytest

from backend.news.miniflux import MinifluxClient
from backend.news.miniflux import MinifluxConfigError
from backend.news.miniflux import MinifluxRequestError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = "response text"

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.headers = {}
        self.auth = None

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def test_client_uses_api_token_header():
    session = FakeSession(FakeResponse([]))

    MinifluxClient(
        base_url="http://miniflux.test",
        api_token="token-123",
        session=session,
    )

    assert session.headers["X-Auth-Token"] == "token-123"
    assert session.auth is None


def test_client_uses_basic_auth_when_token_is_absent():
    session = FakeSession(FakeResponse([]))

    MinifluxClient(
        base_url="http://miniflux.test/",
        username="admin",
        password="secret",
        session=session,
    )

    assert session.auth == ("admin", "secret")


def test_client_requires_authentication():
    with pytest.raises(MinifluxConfigError):
        MinifluxClient(base_url="http://miniflux.test")


def test_list_categories_calls_miniflux_api():
    session = FakeSession(FakeResponse([{"id": 1, "title": "Technology & AI"}]))
    client = MinifluxClient(base_url="http://miniflux.test", api_token="token", session=session)

    categories = client.list_categories()

    assert categories == [{"id": 1, "title": "Technology & AI"}]
    assert session.calls[0]["url"] == "http://miniflux.test/v1/categories"


def test_fetch_recent_entries_calls_entries_endpoint_with_limit():
    session = FakeSession(FakeResponse({"entries": [{"id": 10}], "total": 1}))
    client = MinifluxClient(base_url="http://miniflux.test", api_token="token", session=session)

    payload = client.fetch_recent_entries(limit=25)

    assert payload["entries"] == [{"id": 10}]
    assert session.calls[0]["url"] == "http://miniflux.test/v1/entries"
    assert session.calls[0]["params"] == {
        "direction": "desc",
        "limit": 25,
        "order": "published_at",
    }


def test_request_errors_are_wrapped():
    session = FakeSession(FakeResponse({"error": "nope"}, status_code=500))
    client = MinifluxClient(base_url="http://miniflux.test", api_token="token", session=session)

    with pytest.raises(MinifluxRequestError):
        client.list_categories()

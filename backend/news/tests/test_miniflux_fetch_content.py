from backend.news.miniflux import MinifluxClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.last_url = ""
        self.last_params = None

    def get(self, url, *, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        return FakeResponse(self.payload)


def test_fetch_entry_content_requests_miniflux_endpoint():
    http = FakeSession({"content": "<p>Body</p>"})
    client = MinifluxClient(
        base_url="http://miniflux.test",
        api_token="token",
        session=http,
    )

    content = client.fetch_entry_content(42, update_content=True)

    assert content == "<p>Body</p>"
    assert http.last_url == "http://miniflux.test/v1/entries/42/fetch-content"
    assert http.last_params == {"update_content": "true"}

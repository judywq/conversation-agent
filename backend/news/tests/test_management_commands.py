from dataclasses import dataclass

# ruff: noqa: E501
from io import StringIO

from django.core.management import call_command


@dataclass(frozen=True)
class FakeSyncResult:
    created_count: int = 2
    updated_count: int = 1
    duplicate_url_count: int = 3
    failed: bool = False
    error: str = ""


def test_sync_miniflux_news_command_runs_sync(monkeypatch):
    calls = []

    def fake_sync_recent_articles(*, limit):
        calls.append(limit)
        return FakeSyncResult()

    monkeypatch.setattr("backend.news.management.commands.sync_miniflux_news.sync_recent_articles", fake_sync_recent_articles)

    stdout = StringIO()
    call_command("sync_miniflux_news", "--limit", "50", stdout=stdout)

    assert calls == [50]
    assert "created=2 updated=1 duplicate_urls=3" in stdout.getvalue()

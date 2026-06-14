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


def test_sync_miniflux_news_command_runs_sync_and_classification(monkeypatch):
    sync_calls = []
    classify_calls = []

    def fake_sync_recent_articles(*, limit):
        sync_calls.append(limit)
        return FakeSyncResult()

    def fake_classify_unclassified_articles(*, limit):
        classify_calls.append(limit)
        return 4

    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.sync_recent_articles",
        fake_sync_recent_articles,
    )
    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.classify_unclassified_articles",
        fake_classify_unclassified_articles,
    )

    stdout = StringIO()
    call_command(
        "sync_miniflux_news",
        "--limit",
        "50",
        "--classification-limit",
        "10",
        stdout=stdout,
    )

    assert sync_calls == [50]
    assert classify_calls == [10]
    output = stdout.getvalue()
    assert "created=2 updated=1 duplicate_urls=3" in output
    assert "Classification complete: classified=4" in output


def test_sync_miniflux_news_command_skips_classification_with_no_classify(monkeypatch):
    classify_called = False

    def fake_sync_recent_articles(*, limit):
        return FakeSyncResult()

    def fake_classify_unclassified_articles(*, limit):
        nonlocal classify_called
        classify_called = True
        return 0

    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.sync_recent_articles",
        fake_sync_recent_articles,
    )
    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.classify_unclassified_articles",
        fake_classify_unclassified_articles,
    )

    stdout = StringIO()
    call_command("sync_miniflux_news", "--no-classify", stdout=stdout)

    assert classify_called is False
    assert "Classification complete" not in stdout.getvalue()


def test_sync_miniflux_news_command_skips_classification_when_sync_fails(monkeypatch):
    classify_called = False

    def fake_sync_recent_articles(*, limit):
        return FakeSyncResult(failed=True, error="boom")

    def fake_classify_unclassified_articles(*, limit):
        nonlocal classify_called
        classify_called = True
        return 0

    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.sync_recent_articles",
        fake_sync_recent_articles,
    )
    monkeypatch.setattr(
        "backend.news.management.commands.sync_miniflux_news.classify_unclassified_articles",
        fake_classify_unclassified_articles,
    )

    stderr = StringIO()
    call_command("sync_miniflux_news", stderr=stderr)

    assert classify_called is False
    assert "Miniflux sync failed: boom" in stderr.getvalue()

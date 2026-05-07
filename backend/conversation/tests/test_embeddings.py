from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError
from django.core.management import call_command
from django.test import override_settings
import pytest

from backend.conversation.models import KnowledgeSnippet
from backend.conversation.services.embeddings import (
    build_knowledge_snippet_embedding_text,
)
from backend.conversation.services.embeddings import embedding_text_hash
from backend.conversation.services.embeddings import fake_embedding
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.embeddings import snippet_embedding_is_stale


@pytest.mark.django_db
def test_canonical_text_includes_speech_act_context() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="CDIS01A DIRECTIVES/invite #1",
        content="I wonder whether there are any questions you'd like to ask.",
        source_label="CDIS01A.txt",
        metadata={
            "SA_type": "DIRECTIVES",
            "subtype": "invite",
            "previous_sentence": "Let's pause there.",
            "next_sentence": "Nobody.",
            "file_name": "CDIS01A.txt",
        },
    )

    text = build_knowledge_snippet_embedding_text(snippet)

    assert "Title: CDIS01A DIRECTIVES/invite #1" in text
    assert "Content: I wonder whether there are any questions you'd like to ask." in text
    assert "Source: CDIS01A.txt" in text
    assert "SA_type: DIRECTIVES" in text
    assert "subtype: invite" in text
    assert "previous_sentence: Let's pause there." in text
    assert "next_sentence: Nobody." in text
    assert "file_name: CDIS01A.txt" in text


def test_fake_embedding_is_deterministic_with_default_dimensions() -> None:
    first = fake_embedding("same text")
    second = fake_embedding("same text")

    assert first == second
    assert len(first) == 1536
    assert all(isinstance(value, float) for value in first)


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_stale_returns_true_when_stored_model_differs() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
        embedding=fake_embedding("Course policy"),
        embedding_model="old-model",
        embedding_dimensions=1536,
    )
    snippet.embedding_text_hash = embedding_text_hash(
        build_knowledge_snippet_embedding_text(snippet),
    )

    assert snippet_embedding_is_stale(snippet) is True


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_stale_returns_true_when_stored_dimensions_differ() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
        embedding=fake_embedding("Course policy"),
        embedding_model="fake",
        embedding_dimensions=512,
    )
    snippet.embedding_text_hash = embedding_text_hash(
        build_knowledge_snippet_embedding_text(snippet),
    )

    assert snippet_embedding_is_stale(snippet) is True


@override_settings(EMBEDDING_PROVIDER=" other ")
def test_invalid_provider_raises_runtime_error_without_calling_openai() -> None:
    with patch("backend.conversation.services.embeddings.OpenAI") as openai:
        with pytest.raises(RuntimeError, match="Unsupported EMBEDDING_PROVIDER"):
            generate_embedding("text")

    openai.assert_not_called()


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_refresh_command_generates_missing_embedding() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
    )
    stdout = StringIO()

    call_command("refresh_knowledge_embeddings", stdout=stdout)

    snippet.refresh_from_db()
    assert len(snippet.embedding) == 1536
    assert snippet.embedding_model == "fake"
    assert snippet.embedding_dimensions == 1536
    assert snippet.embedding_text_hash == embedding_text_hash(
        build_knowledge_snippet_embedding_text(snippet),
    )
    assert snippet.embedding_updated_at is not None
    assert "updated=1 dry_run=False" in stdout.getvalue()


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_refresh_command_limit_zero_writes_no_embeddings() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
    )
    stdout = StringIO()

    call_command("refresh_knowledge_embeddings", "--limit", "0", stdout=stdout)

    snippet.refresh_from_db()
    assert snippet.embedding is None
    assert "updated=0 dry_run=False" in stdout.getvalue()


@pytest.mark.django_db
def test_refresh_command_rejects_negative_limit() -> None:
    with pytest.raises(CommandError, match="--limit must be greater than or equal to 0"):
        call_command("refresh_knowledge_embeddings", "--limit", "-1")


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_refresh_command_updates_stale_embedding_when_requested() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
        embedding=fake_embedding("old text"),
        embedding_model="fake",
        embedding_dimensions=1536,
        embedding_text_hash=embedding_text_hash("old text"),
    )
    stdout = StringIO()

    call_command("refresh_knowledge_embeddings", "--stale", stdout=stdout)

    snippet.refresh_from_db()
    assert snippet.embedding_text_hash == embedding_text_hash(
        build_knowledge_snippet_embedding_text(snippet),
    )
    assert list(snippet.embedding) != fake_embedding("old text")
    assert "updated=1 dry_run=False" in stdout.getvalue()


@pytest.mark.django_db
@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_refresh_command_dry_run_does_not_write_embedding() -> None:
    snippet = KnowledgeSnippet.objects.create(
        title="Course policy",
        content="Students may ask for examples.",
        source_label="Course Handbook",
    )
    stdout = StringIO()

    call_command("refresh_knowledge_embeddings", "--dry-run", stdout=stdout)

    snippet.refresh_from_db()
    assert snippet.embedding is None
    assert snippet.embedding_model == ""
    assert snippet.embedding_text_hash == ""
    assert snippet.embedding_updated_at is None
    assert "matched=1 dry_run=True" in stdout.getvalue()

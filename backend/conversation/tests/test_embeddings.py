from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import override_settings
import pytest

from backend.conversation.models import KnowledgeSnippet
from backend.conversation.services.embeddings import (
    build_knowledge_snippet_embedding_text,
)
from backend.conversation.services.embeddings import embedding_text_hash
from backend.conversation.services.embeddings import fake_embedding


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

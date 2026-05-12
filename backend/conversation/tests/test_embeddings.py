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
from backend.conversation.services.embeddings import EmbeddingResult
from backend.conversation.services.embeddings import embedding_text_hash
from backend.conversation.services.embeddings import fake_embedding
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.embeddings import generate_embeddings
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


@override_settings(
    EMBEDDING_PROVIDER="openai",
    EMBEDDING_MODEL="text-embedding-3-small",
    EMBEDDING_DIMENSIONS=1536,
    EMBEDDING_OPENAI_TIMEOUT_SEC=30.0,
    OPENAI_API_KEY="sk-test",
)
def test_generate_embedding_uses_configured_openai_timeout() -> None:
    with patch("backend.conversation.services.embeddings.OpenAI") as openai:
        openai.return_value.embeddings.create.return_value.data = [
            type("EmbeddingData", (), {"embedding": [0.1] * 1536})(),
        ]

        result = generate_embedding("text")

    openai.assert_called_once_with(api_key="sk-test", timeout=30.0)
    assert result.model == "text-embedding-3-small"
    assert result.dimensions == 1536


@override_settings(EMBEDDING_PROVIDER="fake", EMBEDDING_DIMENSIONS=1536)
def test_generate_embeddings_returns_one_result_per_text() -> None:
    results = generate_embeddings(["first", "second"])

    assert [result.text_hash for result in results] == [
        embedding_text_hash("first"),
        embedding_text_hash("second"),
    ]
    assert all(result.model == "fake" for result in results)


@override_settings(
    EMBEDDING_PROVIDER="openai",
    EMBEDDING_MODEL="text-embedding-3-small",
    EMBEDDING_DIMENSIONS=1536,
    EMBEDDING_OPENAI_TIMEOUT_SEC=30.0,
    OPENAI_API_KEY="sk-test",
)
def test_generate_embeddings_batches_openai_inputs() -> None:
    with patch("backend.conversation.services.embeddings.OpenAI") as openai:
        openai.return_value.embeddings.create.return_value.data = [
            type("EmbeddingData", (), {"embedding": [0.1] * 1536})(),
            type("EmbeddingData", (), {"embedding": [0.2] * 1536})(),
        ]

        results = generate_embeddings(["first", "second"])

    openai.return_value.embeddings.create.assert_called_once_with(
        input=["first", "second"],
        model="text-embedding-3-small",
        dimensions=1536,
    )
    assert [result.vector[0] for result in results] == [0.1, 0.2]


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


@pytest.mark.django_db
def test_refresh_command_skip_errors_continues_after_embedding_failure() -> None:
    snippets = [
        KnowledgeSnippet.objects.create(title=f"Snippet {index}", content=f"Text {index}")
        for index in range(3)
    ]
    stdout = StringIO()

    def embedding_or_timeout(text: str) -> EmbeddingResult:
        if "Text 1" in text:
            raise TimeoutError("embedding timeout")
        return EmbeddingResult(
            vector=[0.1] * 1536,
            model="test-embedding",
            dimensions=1536,
            text_hash=embedding_text_hash(text),
        )

    with patch(
        "backend.conversation.management.commands.refresh_knowledge_embeddings.generate_embeddings",
        side_effect=TimeoutError("batch timeout"),
    ), patch(
        "backend.conversation.management.commands.refresh_knowledge_embeddings.generate_embedding",
        side_effect=embedding_or_timeout,
    ):
        call_command("refresh_knowledge_embeddings", "--skip-errors", stdout=stdout)

    for snippet in snippets:
        snippet.refresh_from_db()

    assert snippets[0].embedding is not None
    assert snippets[1].embedding is None
    assert snippets[2].embedding is not None
    assert "updated=2 dry_run=False failed=1" in stdout.getvalue()

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from openai import OpenAI


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    dimensions: int
    text_hash: str


def build_knowledge_snippet_embedding_text(snippet: Any) -> str:
    metadata = snippet.metadata or {}
    parts = [
        ("Title", snippet.title),
        ("Content", snippet.content),
        ("Source", snippet.source_label),
        ("SA_type", metadata.get("SA_type")),
        ("subtype", metadata.get("subtype")),
        ("previous_sentence", metadata.get("previous_sentence")),
        ("next_sentence", metadata.get("next_sentence")),
        ("file_name", metadata.get("file_name")),
    ]
    return "\n".join(
        f"{label}: {value}"
        for label, value in parts
        if value is not None and str(value) != ""
    )


def _stable_metadata_text(metadata: Any) -> str:
    if not isinstance(metadata, dict) or not metadata:
        return ""
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def build_user_memory_embedding_text(memory: Any) -> str:
    parts = [
        ("Content", memory.content),
        ("Memory type", memory.memory_type),
        ("Source label", memory.source_label),
        ("Source URI", memory.source_uri),
        ("Metadata", _stable_metadata_text(memory.metadata)),
    ]
    return "\n".join(
        f"{label}: {value}"
        for label, value in parts
        if value is not None and str(value) != ""
    )


def embedding_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fake_embedding(text: str, dimensions: int = 1536) -> list[float]:
    seed = int(embedding_text_hash(text), 16)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]


def _embedding_provider() -> str:
    provider = str(getattr(settings, "EMBEDDING_PROVIDER", "openai")).strip().casefold()
    if provider not in {"fake", "openai"}:
        raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
    return provider


def _expected_embedding_model(provider: str) -> str:
    if provider == "fake":
        return "fake"
    return str(getattr(settings, "EMBEDDING_MODEL", ""))


def _embedding_dimensions() -> int:
    return int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))


def generate_embedding(text: str) -> EmbeddingResult:
    return generate_embeddings([text])[0]


def generate_embeddings(texts: list[str]) -> list[EmbeddingResult]:
    if not texts:
        return []

    provider = _embedding_provider()
    dimensions = _embedding_dimensions()

    if provider == "fake":
        return [
            EmbeddingResult(
                vector=fake_embedding(text, dimensions=dimensions),
                model="fake",
                dimensions=dimensions,
                text_hash=embedding_text_hash(text),
            )
            for text in texts
        ]

    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required when EMBEDDING_PROVIDER is not 'fake'.",
        )

    model = getattr(settings, "EMBEDDING_MODEL", "")
    timeout = float(getattr(settings, "EMBEDDING_OPENAI_TIMEOUT_SEC", 30.0))
    client = OpenAI(api_key=api_key, timeout=timeout)
    response = client.embeddings.create(
        input=texts,
        model=model,
        dimensions=dimensions,
    )
    return [
        EmbeddingResult(
            vector=list(item.embedding),
            model=model,
            dimensions=dimensions,
            text_hash=embedding_text_hash(text),
        )
        for text, item in zip(texts, response.data, strict=True)
    ]


def snippet_embedding_is_stale(snippet: Any) -> bool:
    provider = _embedding_provider()
    expected_model = _expected_embedding_model(provider)
    expected_dimensions = _embedding_dimensions()
    text = build_knowledge_snippet_embedding_text(snippet)
    return (
        snippet.embedding_text_hash != embedding_text_hash(text)
        or snippet.embedding_model != expected_model
        or snippet.embedding_dimensions != expected_dimensions
    )


def memory_embedding_is_stale(memory: Any) -> bool:
    provider = _embedding_provider()
    expected_model = _expected_embedding_model(provider)
    expected_dimensions = _embedding_dimensions()
    text = build_user_memory_embedding_text(memory)
    return (
        memory.embedding_text_hash != embedding_text_hash(text)
        or memory.embedding_model != expected_model
        or memory.embedding_dimensions != expected_dimensions
    )

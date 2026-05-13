from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from backend.conversation.models import UserMemory
from backend.conversation.services.embeddings import build_user_memory_embedding_text
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.embeddings import generate_embeddings
from backend.conversation.services.embeddings import memory_embedding_is_stale


def _matching_memories(*, include_stale: bool, limit: int | None) -> list[UserMemory]:
    query = UserMemory.objects.filter(is_active=True)
    if not include_stale:
        query = query.filter(embedding__isnull=True)

    memories = []
    for memory in query.order_by("id"):
        if limit is not None and len(memories) >= limit:
            break

        if memory.embedding is None or (
            include_stale and memory_embedding_is_stale(memory)
        ):
            memories.append(memory)
    return memories


def _generate_batch_with_fallback(
    command: BaseCommand,
    batch: list[UserMemory],
    texts: list[str],
) -> tuple[list[Any | None], int]:
    results = []
    failed = 0
    for memory, text in zip(batch, texts, strict=True):
        try:
            results.append(generate_embedding(text))
        except Exception as fallback_exc:  # noqa: BLE001 - --skip-errors is explicit.
            failed += 1
            command.stderr.write(
                command.style.WARNING(
                    f"failed id={memory.id}: "
                    f"{type(fallback_exc).__name__}: {fallback_exc}",
                ),
            )
            results.append(None)
    return results, failed


class Command(BaseCommand):
    help = "Generate or refresh UserMemory embeddings."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--stale",
            action="store_true",
            help=(
                "Also refresh memories whose stored embedding text, model, "
                "or dimensions are stale."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of memories to process.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=int(getattr(settings, "EMBEDDING_BATCH_SIZE", 50)),
            help="Maximum number of memories to send in one embedding request.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count matching memories without writing embeddings.",
        )
        parser.add_argument(
            "--skip-errors",
            action="store_true",
            help="Continue processing later memories when one embedding request fails.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        include_stale = bool(options["stale"])
        dry_run = bool(options["dry_run"])
        skip_errors = bool(options["skip_errors"])
        limit = options["limit"]
        if limit is not None and limit < 0:
            message = "--limit must be greater than or equal to 0"
            raise CommandError(message)

        memories = _matching_memories(include_stale=include_stale, limit=limit)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"matched={len(memories)} dry_run=True"),
            )
            return

        batch_size = int(options["batch_size"])
        if batch_size <= 0:
            message = "--batch-size must be greater than 0"
            raise CommandError(message)

        updated = 0
        failed = 0
        for index in range(0, len(memories), batch_size):
            batch = memories[index : index + batch_size]
            texts = [build_user_memory_embedding_text(memory) for memory in batch]
            try:
                results = generate_embeddings(texts)
            except Exception:
                if not skip_errors:
                    raise
                results, failed_count = _generate_batch_with_fallback(
                    self,
                    batch,
                    texts,
                )
                failed += failed_count

            for memory, result in zip(batch, results, strict=True):
                if result is None:
                    continue
                memory.embedding = result.vector
                memory.embedding_model = result.model
                memory.embedding_dimensions = result.dimensions
                memory.embedding_text_hash = result.text_hash
                memory.embedding_updated_at = timezone.now()
                memory.save(
                    update_fields=[
                        "embedding",
                        "embedding_model",
                        "embedding_dimensions",
                        "embedding_text_hash",
                        "embedding_updated_at",
                        "updated_at",
                    ],
                )
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"updated={updated} dry_run=False failed={failed}"),
        )

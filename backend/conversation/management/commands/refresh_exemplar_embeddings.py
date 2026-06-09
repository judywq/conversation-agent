from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from backend.conversation.models import Exemplar
from backend.conversation.services.embeddings import build_exemplar_embedding_text
from backend.conversation.services.embeddings import exemplar_embedding_is_stale
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.embeddings import generate_embeddings


class Command(BaseCommand):
    help = "Generate or refresh Exemplar embeddings."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--stale",
            action="store_true",
            help="Also refresh exemplars whose stored embedding text, model, or dimensions are stale.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of exemplars to process.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=int(getattr(settings, "EMBEDDING_BATCH_SIZE", 50)),
            help="Maximum number of exemplars to send in one embedding request.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count matching exemplars without writing embeddings.",
        )
        parser.add_argument(
            "--skip-errors",
            action="store_true",
            help="Continue processing later exemplars when one embedding request fails.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        include_stale = bool(options["stale"])
        dry_run = bool(options["dry_run"])
        skip_errors = bool(options["skip_errors"])
        limit = options["limit"]
        if limit is not None and limit < 0:
            raise CommandError("--limit must be greater than or equal to 0")

        query = Exemplar.objects.filter(is_active=True)
        if not include_stale:
            query = query.filter(embedding__isnull=True)

        exemplars = []
        for exemplar in query.order_by("id"):
            if limit is not None and len(exemplars) >= limit:
                break

            if exemplar.embedding is None:
                exemplars.append(exemplar)
            elif include_stale and exemplar_embedding_is_stale(exemplar):
                exemplars.append(exemplar)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"matched={len(exemplars)} dry_run=True"),
            )
            return

        batch_size = int(options["batch_size"])
        if batch_size <= 0:
            raise CommandError("--batch-size must be greater than 0")

        updated = 0
        failed = 0
        for index in range(0, len(exemplars), batch_size):
            batch = exemplars[index : index + batch_size]
            texts = [build_exemplar_embedding_text(exemplar) for exemplar in batch]
            try:
                results = generate_embeddings(texts)
            except Exception:
                if not skip_errors:
                    raise
                results = []
                for exemplar, text in zip(batch, texts, strict=True):
                    try:
                        results.append(generate_embedding(text))
                    except Exception as fallback_exc:
                        failed += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"failed id={exemplar.id} title={exemplar.title!r}: "
                                f"{type(fallback_exc).__name__}: {fallback_exc}",
                            ),
                        )
                        results.append(None)

            for exemplar, result in zip(batch, results, strict=True):
                if result is None:
                    continue
                exemplar.embedding = result.vector
                exemplar.embedding_model = result.model
                exemplar.embedding_dimensions = result.dimensions
                exemplar.embedding_text_hash = result.text_hash
                exemplar.embedding_updated_at = timezone.now()
                exemplar.save(
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

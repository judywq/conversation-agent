from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from backend.conversation.models import KnowledgeSnippet
from backend.conversation.services.embeddings import build_knowledge_snippet_embedding_text
from backend.conversation.services.embeddings import generate_embedding
from backend.conversation.services.embeddings import snippet_embedding_is_stale


class Command(BaseCommand):
    help = "Generate or refresh KnowledgeSnippet embeddings."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--stale",
            action="store_true",
            help="Also refresh snippets whose stored embedding text, model, or dimensions are stale.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of snippets to process.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count matching snippets without writing embeddings.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        include_stale = bool(options["stale"])
        dry_run = bool(options["dry_run"])
        limit = options["limit"]
        if limit is not None and limit < 0:
            raise CommandError("--limit must be greater than or equal to 0")

        query = KnowledgeSnippet.objects.filter(is_active=True)
        if not include_stale:
            query = query.filter(embedding__isnull=True)

        snippets = []
        for snippet in query.order_by("id"):
            if limit is not None and len(snippets) >= limit:
                break

            if snippet.embedding is None:
                snippets.append(snippet)
            elif include_stale and snippet_embedding_is_stale(snippet):
                snippets.append(snippet)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"matched={len(snippets)} dry_run=True"),
            )
            return

        updated = 0
        for snippet in snippets:
            text = build_knowledge_snippet_embedding_text(snippet)
            result = generate_embedding(text)
            snippet.embedding = result.vector
            snippet.embedding_model = result.model
            snippet.embedding_dimensions = result.dimensions
            snippet.embedding_text_hash = result.text_hash
            snippet.embedding_updated_at = timezone.now()
            snippet.save(
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
            self.style.SUCCESS(f"updated={updated} dry_run=False"),
        )

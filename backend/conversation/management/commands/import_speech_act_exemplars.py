from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from backend.conversation.services import speech_act_exemplars


class Command(BaseCommand):
    help = "Import Speech Act annotation JSON into Exemplar records."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("path")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and summarize the import without writing database records.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        summary = speech_act_exemplars.import_speech_act_annotations(
            options["path"],
            dry_run=bool(options["dry_run"]),
        )
        self.stdout.write(
            self.style.SUCCESS(
                " ".join(
                    [
                        f"created={summary.created}",
                        f"skipped={summary.skipped}",
                        f"invalid={summary.invalid}",
                        f"dry_run={summary.dry_run}",
                    ],
                ),
            ),
        )

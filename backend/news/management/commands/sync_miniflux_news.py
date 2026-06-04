from django.conf import settings
from django.core.management.base import BaseCommand

from backend.news.sync import sync_recent_articles


class Command(BaseCommand):
    help = "Synchronize recent Miniflux entries into Django news articles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=settings.NEWS_SYNC_BATCH_SIZE,
            help="Maximum number of recent Miniflux entries to fetch.",
        )

    def handle(self, *args, **options):
        result = sync_recent_articles(limit=options["limit"])
        if result.failed:
            self.stderr.write(self.style.ERROR(f"Miniflux sync failed: {result.error}"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Miniflux sync complete: "
                f"created={result.created_count} "
                f"updated={result.updated_count} "
                f"duplicate_urls={result.duplicate_url_count}",
            ),
        )

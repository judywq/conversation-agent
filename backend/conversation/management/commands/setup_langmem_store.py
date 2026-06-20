from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from backend.conversation.services.langmem_store import setup_langmem_store
from backend.conversation.services.speaker_memories import migrate_legacy_langmem_rows
from backend.conversation.services.speaker_memories import sanitize_all_langmem_memories


class Command(BaseCommand):
    help = "Create LangGraph PostgresStore tables for speaker profiles."

    def handle(self, *args: Any, **options: Any) -> None:
        setup_langmem_store()
        migrated = migrate_legacy_langmem_rows()
        sanitized = sanitize_all_langmem_memories()
        self.stdout.write(self.style.SUCCESS("LangMem store setup complete."))
        if migrated:
            self.stdout.write(f"Migrated {migrated} legacy LangMem row(s) to wrapped format.")
        if sanitized["deleted"] or sanitized["updated"]:
            self.stdout.write(
                "Sanitized LangMem rows: "
                f"deleted={sanitized['deleted']}, "
                f"speaker_fixed={sanitized['updated']}, "
                f"namespaces={sanitized['namespaces']}.",
            )

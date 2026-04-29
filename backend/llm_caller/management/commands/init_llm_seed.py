from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from backend.llm_caller.models import APIKey
from backend.llm_caller.models import LLMModel


class Command(BaseCommand):
    help = (
        "Seed LLM models and API keys from config.settings.base INIT_* settings, "
        "while runtime conversation prompts are loaded from backend/conversation/data/prompts/."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change, without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any):
        dry_run: bool = bool(options["dry_run"])

        init_models = getattr(settings, "INIT_LLM_MODELS", None)
        init_keys = getattr(settings, "INIT_API_KEYS", None)

        init_ok = isinstance(init_models, list) and isinstance(init_keys, list)
        if not init_ok:
            self.stderr.write(
                self.style.WARNING(
                    "INIT_LLM_MODELS and INIT_API_KEYS must both be defined as lists in settings. "
                    "Skipping LLM model and API key seed.",
                ),
            )

        changes: list[str] = []

        with transaction.atomic():
            if init_ok:
                # ---- LLM Models ----
                for item in init_models:
                    if not isinstance(item, dict):
                        continue

                    llm_type = item.get("llm_type")
                    name = item.get("name")
                    if not llm_type or not name:
                        continue

                    defaults = {
                        "display_name": item.get("display_name", name),
                        "is_default": bool(item.get("is_default", False)),
                        "is_active": bool(item.get("is_active", True)),
                        "order": int(item.get("order", 10)),
                    }

                    obj = (
                        LLMModel.objects.filter(llm_type=llm_type, name=name)
                        .order_by("id")
                        .first()
                    )
                    created = False
                    if obj is None:
                        obj = LLMModel(llm_type=llm_type, name=name, **defaults)
                        created = True
                    else:
                        for k, v in defaults.items():
                            setattr(obj, k, v)

                    changes.append(
                        f"LLMModel {'CREATE' if created else 'UPDATE'} {llm_type}:{name}",
                    )

                    if not dry_run:
                        obj.save()

                # ---- API Keys ----
                for idx, item in enumerate(init_keys):
                    if not isinstance(item, dict):
                        continue

                    llm_type = item.get("llm_type")
                    name = item.get("name")
                    key = item.get("key", "")
                    if not llm_type or not name:
                        continue

                    defaults = {
                        "key": str(key or ""),
                        "is_active": bool(key),
                        "order": idx + 1,
                    }

                    obj = (
                        APIKey.objects.filter(llm_type=llm_type, name=name)
                        .order_by("id")
                        .first()
                    )
                    created = False
                    if obj is None:
                        obj = APIKey(llm_type=llm_type, name=name, **defaults)
                        created = True
                    else:
                        for k, v in defaults.items():
                            setattr(obj, k, v)

                    changes.append(f"APIKey {'CREATE' if created else 'UPDATE'} {llm_type}:{name}")

                    if not dry_run:
                        obj.save()

            if dry_run:
                transaction.set_rollback(True)

        for line in changes:
            self.stdout.write(line)

        self.stdout.write(
            self.style.SUCCESS("Done." if not dry_run else "Dry-run complete (no changes written)."),
        )


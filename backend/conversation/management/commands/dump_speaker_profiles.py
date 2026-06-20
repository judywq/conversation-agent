from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from backend.conversation.services.speaker_profiles import dump_all_profiles


class Command(BaseCommand):
    help = "Print LangMem speaker profiles for a user."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("user_id", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        user_model = get_user_model()
        user_id = int(options["user_id"])
        try:
            user = user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"User {user_id} not found.") from exc
        payload = dump_all_profiles(user)
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

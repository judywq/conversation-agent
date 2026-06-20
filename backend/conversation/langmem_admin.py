from __future__ import annotations

import json

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from backend.conversation.models import AgentProfile
from backend.conversation.models import LangMemMemory
from backend.conversation.services.speaker_memories import LangMemAdminEntry
from backend.conversation.services.speaker_memories import get_langmem_entry_for_admin
from backend.conversation.services.speaker_memories import langmem_enabled
from backend.conversation.services.speaker_memories import list_langmem_entries_for_admin
from backend.conversation.services.speaker_profile_schemas import EXTRACTABLE_MEMORY_TYPES

User = get_user_model()
PAGE_SIZE = 50


@admin.register(LangMemMemory)
class LangMemMemoryAdmin(admin.ModelAdmin):
    change_list_template = "admin/conversation/langmemmemory/change_list.html"
    detail_template = "admin/conversation/langmemmemory/detail.html"

    def has_module_permission(self, request) -> bool:
        return request.user.is_staff

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_queryset(self, request):
        return LangMemMemory.objects.none()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<str:entry_id>/",
                self.admin_site.admin_view(self.detail_view),
                name="conversation_langmemmemory_detail",
            ),
        ]
        return custom_urls + urls

    def _active_filters(self, request) -> dict[str, str]:
        return {
            "user_id": (request.GET.get("user_id") or "").strip(),
            "memory_type": (request.GET.get("memory_type") or "").strip(),
            "namespace_kind": (request.GET.get("namespace_kind") or "").strip(),
            "agent_slug": (request.GET.get("agent_slug") or "").strip(),
            "q": (request.GET.get("q") or "").strip(),
        }

    def _user_links(self, entries: list[LangMemAdminEntry]) -> dict[int, str]:
        user_ids = {entry.user_id for entry in entries if entry.user_id is not None}
        links: dict[int, str] = {}
        for user in User.objects.filter(id__in=user_ids).only("id", "email", "name", "username"):
            url = reverse("admin:users_user_change", args=[user.pk])
            label = (user.email or user.username or user.name or str(user.pk)).strip()
            links[user.pk] = format_html('<a href="{}">{}</a>', url, label)
        return links

    def _agent_display_names(
        self,
        entries: list[LangMemAdminEntry],
    ) -> dict[tuple[int, str], str]:
        pairs = {
            (entry.user_id, entry.agent_slug)
            for entry in entries
            if entry.user_id is not None and entry.agent_slug
        }
        if not pairs:
            return {}

        user_ids = {user_id for user_id, _ in pairs}
        slugs = {slug for _, slug in pairs}
        names: dict[tuple[int, str], str] = {}

        for entry in entries:
            if entry.user_id is None or not entry.agent_slug:
                continue
            meta = entry.metadata if isinstance(entry.metadata, dict) else {}
            if meta.get("field") == "display_name":
                value = (meta.get("value") or "").strip()
                if value:
                    names[(entry.user_id, entry.agent_slug)] = value

        profiles = (
            AgentProfile.objects.filter(
                session__user_id__in=user_ids,
                agent_id__in=slugs,
            )
            .exclude(display_name="")
            .order_by("-updated_at")
            .values("session__user_id", "agent_id", "display_name")
        )
        for row in profiles:
            key = (row["session__user_id"], row["agent_id"])
            if key not in names and row["display_name"]:
                names[key] = row["display_name"].strip()
        return names

    def _resolve_speaker_display(
        self,
        entry: LangMemAdminEntry,
        *,
        agent_names: dict[tuple[int, str], str],
        user_names: dict[int, str],
    ) -> str:
        speaker = (entry.speaker or "").strip()
        if speaker == "user":
            if entry.user_id is not None and entry.user_id in user_names:
                return user_names[entry.user_id]
            return "User"
        if entry.user_id is not None and entry.agent_slug:
            return agent_names.get((entry.user_id, entry.agent_slug), speaker)
        return speaker or "—"

    def _user_preferred_names(self, user_ids: set[int]) -> dict[int, str]:
        names: dict[int, str] = {}
        for user in User.objects.filter(id__in=user_ids).select_related("userprofile").only(
            "id",
            "name",
            "username",
            "userprofile__preferred_name",
        ):
            profile = getattr(user, "userprofile", None)
            preferred = (getattr(profile, "preferred_name", "") or "").strip() if profile else ""
            label = preferred or (user.name or "").strip() or (user.username or "").strip()
            if label:
                names[user.pk] = label
        return names

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        opts = self.model._meta
        filters = self._active_filters(request)
        enabled = langmem_enabled()
        entries: list[LangMemAdminEntry] = []
        error_message = ""

        if enabled:
            try:
                entries = list_langmem_entries_for_admin(
                    user_id=filters["user_id"] or None,
                    memory_type=filters["memory_type"] or None,
                    namespace_kind=filters["namespace_kind"] or None,
                    agent_slug=filters["agent_slug"] or None,
                    query=filters["q"] or None,
                )
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
        else:
            error_message = _("LangMem is disabled (SPEAKER_PROFILES_ENABLED or LANGMEM_ENABLED is false).")

        paginator = Paginator(entries, PAGE_SIZE)
        page_number = request.GET.get("p") or 1
        page_obj = paginator.get_page(page_number)
        page_entries = list(page_obj.object_list)
        user_links = self._user_links(page_entries)
        agent_names = self._agent_display_names(page_entries)
        user_ids = {entry.user_id for entry in page_entries if entry.user_id is not None}
        user_names = self._user_preferred_names(user_ids)
        display_rows = [
            {
                "entry": entry,
                "user_html": user_links.get(entry.user_id, str(entry.user_id) if entry.user_id else "—"),
                "role": entry.agent_slug or "—",
                "speaker_display": self._resolve_speaker_display(
                    entry,
                    agent_names=agent_names,
                    user_names=user_names,
                ),
            }
            for entry in page_entries
        ]

        context = {
            **self.admin_site.each_context(request),
            **extra_context,
            "opts": opts,
            "app_label": opts.app_label,
            "title": opts.verbose_name_plural,
            "enabled": enabled,
            "error_message": error_message,
            "display_rows": display_rows,
            "page_obj": page_obj,
            "paginator": paginator,
            "total_count": paginator.count,
            "filters": filters,
            "memory_types": sorted(EXTRACTABLE_MEMORY_TYPES),
            "namespace_kinds": ["user", "agent", "relationship"],
            "has_add_permission": False,
            "cl": None,
        }
        return TemplateResponse(request, self.change_list_template, context)

    def detail_view(self, request, entry_id: str, extra_context=None):
        entry = get_langmem_entry_for_admin(entry_id)
        if entry is None:
            raise Http404("LangMem entry not found.")

        opts = self.model._meta
        user_link = ""
        if entry.user_id is not None:
            try:
                user = User.objects.select_related("userprofile").get(pk=entry.user_id)
                user_url = reverse("admin:users_user_change", args=[user.pk])
                label = (user.email or user.username or user.name or str(user.pk)).strip()
                user_link = format_html('<a href="{}">{}</a>', user_url, label)
            except User.DoesNotExist:
                user_link = str(entry.user_id)

        agent_names = self._agent_display_names([entry])
        user_names = (
            self._user_preferred_names({entry.user_id})
            if entry.user_id is not None
            else {}
        )
        speaker_display = self._resolve_speaker_display(
            entry,
            agent_names=agent_names,
            user_names=user_names,
        )

        context = {
            **self.admin_site.each_context(request),
            **(extra_context or {}),
            "opts": opts,
            "app_label": opts.app_label,
            "title": _("LangMem memory detail"),
            "entry": entry,
            "entry_json": json.dumps(
                {
                    "store_key": entry.store_key,
                    "namespace": entry.namespace_path,
                    "user_id": entry.user_id,
                    "namespace_kind": entry.namespace_kind,
                    "agent_slug": entry.agent_slug,
                    "memory_type": entry.memory_type,
                    "content": entry.content,
                    "confidence": entry.confidence,
                    "speaker": entry.speaker,
                    "source_label": entry.source_label,
                    "metadata": entry.metadata,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "user_link": user_link,
            "speaker_display": speaker_display,
            "role": entry.agent_slug or "—",
            "changelist_url": reverse("admin:conversation_langmemmemory_changelist"),
        }
        return TemplateResponse(request, self.detail_template, context)

    @staticmethod
    def content_excerpt(entry: LangMemAdminEntry) -> str:
        return Truncator(entry.content).chars(100, truncate="...")

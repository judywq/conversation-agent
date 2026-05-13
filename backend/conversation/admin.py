from django.contrib import admin
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from .models import ConversationLLMPrompt
from .models import KnowledgeSnippet
from .models import TurnRetrieval
from .models import UserMemory


class MetadataValueListFilter(admin.SimpleListFilter):
    metadata_key = ""
    allowed_values = None

    def lookups(self, request, model_admin):
        values = set()
        queryset = model_admin.get_queryset(request)
        for metadata in queryset.values_list("metadata", flat=True):
            if not isinstance(metadata, dict):
                continue

            value = metadata.get(self.metadata_key)
            if value in (None, ""):
                continue

            normalized_value = str(value)
            if (
                self.allowed_values is not None
                and normalized_value not in self.allowed_values
            ):
                continue

            values.add(normalized_value)

        return sorted((value, value) for value in values)

    def queryset(self, request, queryset):
        if self.value():
            if (
                self.allowed_values is not None
                and self.value() not in self.allowed_values
            ):
                return queryset.none()
            return queryset.filter(**{f"metadata__{self.metadata_key}": self.value()})
        return queryset


class ExemplarKindListFilter(MetadataValueListFilter):
    title = _("Exemplar kind")
    parameter_name = "metadata_kind"
    metadata_key = "kind"
    allowed_values = {"speech_act_exemplar"}


class SpeechActTypeListFilter(MetadataValueListFilter):
    title = _("Speech Act type")
    parameter_name = "metadata_sa_type"
    metadata_key = "SA_type"


class SpeechActSubtypeListFilter(MetadataValueListFilter):
    title = _("Subtype")
    parameter_name = "metadata_subtype"
    metadata_key = "subtype"


class SourceFileListFilter(MetadataValueListFilter):
    title = _("Source file")
    parameter_name = "metadata_file_name"
    metadata_key = "file_name"


@admin.register(KnowledgeSnippet)
class KnowledgeSnippetAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "content_excerpt",
        "metadata_kind",
        "metadata_sa_type",
        "metadata_subtype",
        "metadata_file_name",
        "source_label",
        "source_uri",
        "is_active",
        "has_embedding",
        "embedding_model",
        "embedding_updated_at",
        "updated_at",
    ]
    list_display_links = ["title", "id"]
    list_filter = [
        "is_active",
        "source_label",
        ExemplarKindListFilter,
        SpeechActTypeListFilter,
        SpeechActSubtypeListFilter,
        SourceFileListFilter,
    ]
    search_fields = [
        "title",
        "content",
        "source_label",
        "source_uri",
        "metadata__kind",
        "metadata__SA_type",
        "metadata__subtype",
        "metadata__file_name",
    ]
    actions = ["enable_selected_snippets", "disable_selected_snippets"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("title", "content", "is_active")}),
        ("Source", {"fields": ("source_label", "source_uri", "metadata")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Kind")
    def metadata_kind(self, obj):
        return self._metadata_value(obj, "kind")

    @admin.display(description="Content")
    def content_excerpt(self, obj):
        return Truncator(obj.content).chars(80, truncate="...")

    @admin.display(boolean=True, description="Embedding")
    def has_embedding(self, obj: KnowledgeSnippet) -> bool:
        return obj.embedding is not None

    @admin.display(description="SA type")
    def metadata_sa_type(self, obj):
        return self._metadata_value(obj, "SA_type")

    @admin.display(description="Subtype")
    def metadata_subtype(self, obj):
        return self._metadata_value(obj, "subtype")

    @admin.display(description="Source file")
    def metadata_file_name(self, obj):
        return self._metadata_value(obj, "file_name")

    @admin.action(description="Enable selected snippets")
    def enable_selected_snippets(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Enabled {updated} snippet(s).")

    @admin.action(description="Disable selected snippets")
    def disable_selected_snippets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Disabled {updated} snippet(s).")

    def _metadata_value(self, obj, key):
        metadata = obj.metadata if isinstance(obj.metadata, dict) else {}
        return metadata.get(key, "")


@admin.register(UserMemory)
class UserMemoryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "memory_type",
        "content_excerpt",
        "source_label",
        "source_uri",
        "confidence",
        "is_active",
        "has_embedding",
        "embedding_model",
        "embedding_updated_at",
        "updated_at",
    ]
    list_display_links = ["id", "content_excerpt"]
    list_filter = [
        "is_active",
        "memory_type",
        "confidence",
        "updated_at",
        "user",
    ]
    search_fields = [
        "content",
        "memory_type",
        "source_label",
        "source_uri",
        "user__email",
        "user__username",
        "user__name",
    ]
    actions = ["enable_selected_memories", "disable_selected_memories"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "embedding_model",
        "embedding_dimensions",
        "embedding_text_hash",
        "embedding_updated_at",
    ]
    fieldsets = (
        (
            None,
            {"fields": ("user", "content", "memory_type", "confidence", "is_active")},
        ),
        ("Source", {"fields": ("source_label", "source_uri", "metadata")}),
        (
            "Embedding",
            {
                "fields": (
                    "embedding_model",
                    "embedding_dimensions",
                    "embedding_text_hash",
                    "embedding_updated_at",
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Content")
    def content_excerpt(self, obj: UserMemory) -> str:
        return Truncator(obj.content).chars(80, truncate="...")

    @admin.display(boolean=True, description="Embedding")
    def has_embedding(self, obj: UserMemory) -> bool:
        return obj.embedding is not None

    @admin.action(description="Enable selected memories")
    def enable_selected_memories(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Enabled {updated} memory record(s).")

    @admin.action(description="Disable selected memories")
    def disable_selected_memories(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Disabled {updated} memory record(s).")


@admin.register(TurnRetrieval)
class TurnRetrievalAdmin(admin.ModelAdmin):
    list_display = ["id", "turn", "query", "created_at"]
    list_display_links = ["id", "turn"]
    search_fields = ["query", "rendered_context", "error_message"]
    readonly_fields = [
        "turn",
        "query",
        "requested_sources",
        "source_statuses",
        "items",
        "rendered_context",
        "error_message",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConversationLLMPrompt)
class ConversationLLMPromptAdmin(admin.ModelAdmin):
    list_display = ["id", "key", "created_at", "updated_at"]
    list_display_links = ["key", "id"]
    search_fields = ["key", "system_template", "user_template"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("key",)}),
        ("Templates", {"fields": ("system_template", "user_template")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )

from django.contrib import admin

from .models import ConversationLLMPrompt
from .models import KnowledgeSnippet
from .models import TurnRetrieval


@admin.register(KnowledgeSnippet)
class KnowledgeSnippetAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "source_label", "source_uri", "is_active", "updated_at"]
    list_display_links = ["title", "id"]
    list_filter = ["is_active", "source_label"]
    search_fields = ["title", "content", "source_label", "source_uri"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("title", "content", "is_active")}),
        ("Source", {"fields": ("source_label", "source_uri", "metadata")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


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

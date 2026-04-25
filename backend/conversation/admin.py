from django.contrib import admin

from .models import ConversationLLMPrompt


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

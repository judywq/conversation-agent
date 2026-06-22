from django.apps import AppConfig


class ConversationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.conversation"

    def ready(self) -> None:
        import backend.conversation.admin
        import backend.conversation.langmem_admin  # noqa: F401
        import backend.conversation.langmem_signals  # noqa: F401
        import backend.conversation.argument_summary_signals  # noqa: F401
        import backend.conversation.user_memory_signals  # noqa: F401

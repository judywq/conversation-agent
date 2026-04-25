from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("conversation", "0003_conversationsession_user_override_requested"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversationLLMPrompt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "key",
                    models.SlugField(
                        help_text="Stable id, e.g. agent_utterance or facilitator_plan",
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "system_template",
                    models.TextField(help_text="str.format template for the system message"),
                ),
                (
                    "user_template",
                    models.TextField(
                        blank=True,
                        help_text="str.format template for the user/human message. If empty, facilitator uses a JSON body at runtime.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Conversation LLM prompt",
                "verbose_name_plural": "Conversation LLM prompts",
                "ordering": ["key"],
            },
        ),
    ]

# ruff: noqa: PERF401

from typing import Literal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.core.validators import URLValidator
from django.db import models
from langchain_core.prompts import ChatPromptTemplate

from backend.core.models import TimestampedBase

User = get_user_model()


LLM_TYPE_CHOICES = [
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("groq", "Groq"),
    ("deepseek", "DeepSeek"),
    ("gemini", "Gemini"),
    ("custom", "Custom"),
]


class LLMModel(TimestampedBase):
    order = models.IntegerField(
        default=10,
        help_text="Order of the model in the UI (smaller number comes first)",
    )
    name = models.CharField(
        max_length=200,
        help_text=(
            "The model name for calling the LLM API (e.g., gpt-4o-2024-11-20)."
            " Check <a href='https://platform.openai.com/docs/models#current-model-aliases'"
            " target='_blank'>OpenAI</a>, "
            " <a href='https://docs.anthropic.com/en/docs/about-claude/models'"
            " target='_blank'>Anthropic</a>, "
            " <a href='https://console.groq.com/docs/models'"
            " target='_blank'>Groq</a>, "
            " <a href='https://api-docs.deepseek.com/quick_start/pricing'"
            " target='_blank'>DeepSeek</a> "
            " for model list."
        ),
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Display name for the model (e.g., GPT-4o)",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="This model will be pre-selected in the UI",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active models will be listed in the UI",
    )
    llm_type = models.CharField(
        max_length=20,
        choices=LLM_TYPE_CHOICES,
        default="openai",
        help_text="The type of LLM service to use",
    )
    url = models.URLField(
        max_length=500,
        blank=True,
        help_text=(
            "URL for custom LLM service "
            "(e.g., http://host.docker.internal:8080/v1). "
            "Leave empty for OpenAI."
        ),
        validators=[URLValidator()],
    )

    class Meta:
        ordering = ["order"]
        get_latest_by = "created_at"

    def __str__(self):
        return (
            f"{self.llm_type}: {self.display_name} "
            f"({'Active' if self.is_active else 'Inactive'})"
        )

    def save(self, *args, **kwargs):
        # If this model is being set as default, reset all others
        if self.is_default:
            LLMModel.objects.exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_models(cls):
        return cls.objects.filter(is_active=True)

    def clean(self):
        super().clean()
        if self.llm_type == "custom" and not self.url:
            raise ValidationError(
                {"url": "URL is required for custom LLM services"},
            )


class QuotaConfig(TimestampedBase):
    model = models.OneToOneField(
        LLMModel,
        on_delete=models.CASCADE,
        related_name="quota_config",
        help_text="The LLM model this quota applies to",
    )
    daily_limit = models.IntegerField(
        default=10,
        help_text="Maximum number of requests per day for this model",
    )

    class Meta:
        get_latest_by = "created_at"

    def __str__(self):
        return f"QuotaConfig({self.model.display_name}, limit={self.daily_limit})"


class LLMConfig(TimestampedBase):
    PURPOSE_CHOICES = [
        ("generic", "Generic"),
        ("chat", "Chat"),
        ("summarization", "Summarization"),
        ("extraction", "Extraction"),
    ]

    purpose = models.CharField(
        max_length=50,
        choices=PURPOSE_CHOICES,
        help_text="The purpose of this configuration",
    )
    model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        related_name="llm_configs",
        help_text="The LLM model this config applies to",
        null=True,
    )
    system_prompt = models.TextField(
        help_text="The system prompt for the LLM.",
    )
    temperature = models.FloatField(
        default=0.7,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(2.0),
        ],
        help_text="Value between 0 and 2",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only one config can be active per purpose",
    )

    class Meta:
        get_latest_by = "created_at"

    def __str__(self):
        return f"LLM Config ({self.get_purpose_display()}, Updated: {self.updated_at})"

    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate other configs with the same purpose
            LLMConfig.objects.filter(purpose=self.purpose).exclude(id=self.id).update(
                is_active=False,
            )
        super().save(*args, **kwargs)

    @classmethod
    def get_active_config(
        cls,
        purpose: str,
    ):
        """Get the active config for the given purpose."""
        try:
            return cls.objects.get(purpose=purpose, is_active=True)
        except cls.DoesNotExist:
            msg = (
                f"No active config found for purpose: {purpose}."
                f"Please create one in the admin panel."
            )
            raise ValueError(msg) from None

    @classmethod
    def get_active_config_with_demo_fallback(
        cls,
        purpose: str,
        is_demo: bool = False,  # noqa: FBT001, FBT002
    ):
        """Get the active config for the given purpose, with demo fallback.

        If is_demo is True, tries to get a demo config first, then falls back to normal.
        If is_demo is False, gets the normal config.
        """
        if is_demo:
            # Try to get demo config first
            try:
                demo_purpose = f"{purpose}_demo"
                return cls.objects.get(purpose=demo_purpose, is_active=True)
            except cls.DoesNotExist:
                # Fall back to normal config
                pass

        # Get normal config
        return cls.get_active_config(purpose=purpose)

    def get_prompt_template(self):
        """Get a ChatPromptTemplate for this config."""
        return ChatPromptTemplate.from_template(self.system_prompt)


class APIKey(TimestampedBase):
    key = models.CharField(
        max_length=255,
        help_text="API Key (e.g., 'sk-...')",
    )
    name = models.CharField(
        max_length=100,
        help_text="A name to identify this key (e.g., 'Primary Key', 'Backup Key')",
    )
    llm_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        related_name="api_keys",
        help_text="The LLM model this key applies to",
        blank=True,
        null=True,
    )
    llm_type = models.CharField(
        max_length=20,
        choices=LLM_TYPE_CHOICES,
        blank=True,
        help_text="The type of LLM service to use",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active keys will be used",
    )
    order = models.IntegerField(
        default=10,
        validators=[MinValueValidator(0)],
        help_text="Keys with lower order values will be used first",
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"

    @classmethod
    def get_available_key(cls, model_name: str):
        """Get the first available active key."""
        found = (
            cls.objects.filter(
                is_active=True,
                llm_model__name=model_name,
            )
            .order_by("order")
            .first()
        )

        if found:
            return found

        try:
            llm_model = LLMModel.objects.get(name=model_name)
        except LLMModel.DoesNotExist:
            msg = f"LLM model {model_name} does not exist"
            raise ValueError(msg) from None

        return (
            cls.objects.filter(
                is_active=True,
                llm_type=llm_model.llm_type,
            )
            .order_by("order")
            .first()
        )

    def clean(self):
        super().clean()
        if self.llm_type == "custom" and not self.llm_model:
            raise ValidationError(
                {"llm_model": "LLM model is required for custom LLM services"},
            )

        if not self.llm_model and not self.llm_type:
            raise ValidationError(
                {"llm_model": "LLM model or LLM type is required"},
            )

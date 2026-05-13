import pytest
from django.core.exceptions import ValidationError

from backend.llm_caller.models import LLMConfig
from backend.llm_caller.models import LLMModel
from backend.llm_caller.models import QuotaConfig

pytestmark = pytest.mark.django_db


class TestLLMModel:
    def test_str_representation(self):
        model = LLMModel.objects.create(
            name="gpt-4",
            display_name="GPT-4",
            is_active=True,
        )

        assert str(model) == "openai: GPT-4 (Active)"

    def test_save_default_model(self):
        model1 = LLMModel.objects.create(
            name="gpt-4",
            display_name="GPT-4",
            is_default=True,
        )

        model2 = LLMModel.objects.create(
            name="gpt-3.5",
            display_name="GPT-3.5",
            is_default=True,
        )

        model1.refresh_from_db()
        model2.refresh_from_db()

        assert not model1.is_default
        assert model2.is_default

    def test_get_active_models(self):
        LLMModel.objects.create(
            name="gpt-4",
            display_name="GPT-4",
            is_active=False,
        )
        active_model = LLMModel.objects.create(
            name="gpt-3.5",
            display_name="GPT-3.5",
            is_active=True,
        )

        assert list(LLMModel.get_active_models()) == [active_model]

    def test_custom_model_requires_url(self):
        model = LLMModel(
            name="local",
            display_name="Local Model",
            llm_type="custom",
        )

        with pytest.raises(ValidationError):
            model.full_clean()


class TestLLMConfig:
    def test_get_active_config(self):
        inactive = LLMConfig.objects.create(
            purpose="chat",
            system_prompt="Inactive prompt",
            is_active=False,
        )
        active = LLMConfig.objects.create(
            purpose="chat",
            system_prompt="Active prompt",
            is_active=True,
        )

        assert LLMConfig.get_active_config("chat") == active
        assert inactive.is_active is False

    def test_get_active_config_raises_when_missing(self):
        with pytest.raises(ValueError, match="No active config found"):
            LLMConfig.get_active_config("chat")

    def test_activating_config_disables_previous_config_for_same_purpose(self):
        first = LLMConfig.objects.create(
            purpose="chat",
            system_prompt="First prompt",
            is_active=True,
        )

        second = LLMConfig.objects.create(
            purpose="chat",
            system_prompt="Second prompt",
            is_active=True,
        )

        first.refresh_from_db()

        assert first.is_active is False
        assert second.is_active is True


class TestQuotaConfig:
    def test_str_representation(self):
        model = LLMModel.objects.create(
            name="gpt-4",
            display_name="GPT-4",
        )
        quota = QuotaConfig.objects.create(
            model=model,
            daily_limit=100,
        )

        assert str(quota) == "QuotaConfig(GPT-4, limit=100)"

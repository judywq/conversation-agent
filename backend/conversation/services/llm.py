from django.conf import settings

from backend.llm_caller.models import APIKey
from backend.llm_caller.models import LLMModel
from backend.llm_caller.utils import get_llm_model
from backend.conversation.exceptions import ServiceConfigurationError


def get_default_chat_llm():
    """
    Minimal integration with existing LLM registry.

    Later we can map purposes (facilitator vs agent) to LLMConfig entries.
    """
    model = LLMModel.objects.filter(is_active=True, is_default=True).first()
    if model is None:
        model = LLMModel.objects.filter(is_active=True).order_by("order").first()
    if model is None:
        raise ServiceConfigurationError(
            "No active LLM models are configured.",
            code="LLM_MODEL_NOT_CONFIGURED",
        )

    key = APIKey.get_available_key(model.name)
    if key is None or not key.key:
        raise ServiceConfigurationError(
            "LLM API key is not configured. Please set it in admin panel.",
            code="LLM_API_KEY_MISSING",
        )

    config = {
        "llm_type": model.llm_type,
        "model_name": model.name,
        "key": key,
        "url": model.url,
        "temperature": 0.7,
    }
    return get_llm_model(config, fake=settings.FAKE_LLM_REQUEST)


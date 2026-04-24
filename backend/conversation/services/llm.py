from django.conf import settings

from backend.llm_caller.models import APIKey
from backend.llm_caller.models import LLMModel
from backend.llm_caller.utils import get_llm_model


def get_default_chat_llm():
    """
    Minimal integration with existing LLM registry.

    Later we can map purposes (facilitator vs agent) to LLMConfig entries.
    """
    model = LLMModel.objects.filter(is_active=True, is_default=True).first()
    if model is None:
        model = LLMModel.objects.filter(is_active=True).order_by("order").first()
    if model is None:
        raise RuntimeError("No active LLM models configured")

    key = APIKey.get_available_key(model.name)
    if key is None or not key.key:
        raise RuntimeError("No API key configured for the default LLM model")

    config = {
        "llm_type": model.llm_type,
        "model_name": model.name,
        "key": key,
        "url": model.url,
        "temperature": 0.7,
    }
    return get_llm_model(config, fake=settings.FAKE_LLM_REQUEST)


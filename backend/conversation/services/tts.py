from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from openai import OpenAI

from backend.llm_caller.models import APIKey
from backend.conversation.exceptions import ServiceConfigurationError


def _get_openai_key() -> str:
    key_obj = APIKey.objects.filter(is_active=True, llm_type="openai").order_by("order").first()
    if key_obj and key_obj.key:
        return key_obj.key
    key_obj = APIKey.objects.filter(is_active=True, llm_model__llm_type="openai").order_by("order").first()
    if key_obj and key_obj.key:
        return key_obj.key
    raise ServiceConfigurationError(
        "TTS requires an OpenAI API key, but none is configured. Please set it in admin panel.",
        code="TTS_API_KEY_MISSING",
    )


def synthesize_speech(
    *,
    text: str,
    voice: str = "alloy",
    model: str = "gpt-4o-mini-tts",
    audio_format: str = "mp3",
) -> str:
    """
    Generates speech audio, stores it under MEDIA_ROOT, and returns a public URL.
    """
    client = OpenAI(api_key=_get_openai_key())
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format=audio_format,
    )
    audio_bytes = response.read()

    file_name = f"audio/{uuid4().hex}.{audio_format}"
    path = default_storage.save(file_name, ContentFile(audio_bytes))

    domain = settings.DOMAIN_NAME
    if not domain.startswith("http"):
        domain = f"http://{domain}"
    return f"{domain}{settings.MEDIA_URL}{path}"


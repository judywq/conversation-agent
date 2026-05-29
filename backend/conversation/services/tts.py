import logging
import time
from typing import Callable
from uuid import uuid4

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from openai import OpenAI

from backend.conversation.exceptions import ServiceConfigurationError
from backend.llm_caller.models import APIKey

logger = logging.getLogger(__name__)

_TTS_RETRY_BACKOFFS_SEC = (0.5, 1.0)


def _retry_tts_call(
    call: Callable[[], bytes],
    *,
    retry_on: tuple[type[BaseException], ...],
    provider: str,
) -> bytes:
    """
    Retry a TTS HTTP call on transient connection-layer errors (TLS handshake
    drops, connection resets). Backoffs of 0.5s and 1.0s — two retries max.
    Does NOT retry on HTTP status errors (4xx/5xx); those are deterministic.
    """
    total_attempts = len(_TTS_RETRY_BACKOFFS_SEC) + 1
    for attempt in range(total_attempts):
        try:
            return call()
        except retry_on as exc:
            if attempt == total_attempts - 1:
                logger.warning(
                    "tts_retry_exhausted provider=%s attempts=%d error=%s",
                    provider, total_attempts, type(exc).__name__,
                )
                raise
            sleep_for = _TTS_RETRY_BACKOFFS_SEC[attempt]
            logger.warning(
                "tts_retry provider=%s attempt=%d/%d backoff=%.1f error=%s",
                provider, attempt + 1, total_attempts, sleep_for, type(exc).__name__,
            )
            time.sleep(sleep_for)
    raise RuntimeError("unreachable")


OPENAI_BUILTIN_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}


def tts_provider_timeouts(provider: str | None = None) -> tuple[float, float]:
    selected = str(provider or getattr(settings, "TTS_PROVIDER", "openai") or "openai").lower()
    if selected == "elevenlabs":
        connect = float(getattr(settings, "ELEVENLABS_TTS_CONNECT_TIMEOUT_SEC", 15.0))
        read = float(getattr(settings, "ELEVENLABS_TTS_TIMEOUT_SEC", 90.0))
        return connect, read
    if selected == "fish":
        connect = float(getattr(settings, "FISH_TTS_CONNECT_TIMEOUT_SEC", 15.0))
        read = float(getattr(settings, "FISH_TTS_TIMEOUT_SEC", 90.0))
        return connect, read
    return 15.0, 90.0


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
    voice: str | None = None,
    model: str | None = None,
    audio_format: str | None = None,
) -> str:
    """
    Generates speech audio, stores it under MEDIA_ROOT, and returns a public URL.
    """
    provider = str(getattr(settings, "TTS_PROVIDER", "openai") or "openai").lower()
    if provider == "fish":
        selected_format = audio_format or settings.FISH_TTS_FORMAT
        audio_bytes = _synthesize_fish_speech(
            text=text,
            voice=voice,
            model=model or settings.FISH_TTS_MODEL,
            audio_format=selected_format,
        )
    elif provider == "elevenlabs":
        selected_format = audio_format or "mp3"
        audio_bytes = _synthesize_elevenlabs_speech(
            text=text,
            voice=voice,
            model=model or settings.ELEVENLABS_MODEL_ID,
            output_format=audio_format or settings.ELEVENLABS_OUTPUT_FORMAT,
        )
    elif provider == "openai":
        selected_format = audio_format or "mp3"
        audio_bytes = _synthesize_openai_speech(
            text=text,
            voice=voice or settings.OPENAI_TTS_VOICE,
            model=model or settings.OPENAI_TTS_MODEL,
            audio_format=selected_format,
        )
    else:
        raise ServiceConfigurationError(
            f"Unsupported TTS_PROVIDER '{provider}'. Expected 'openai', 'fish', or 'elevenlabs'.",
            code="TTS_PROVIDER_UNSUPPORTED",
        )

    file_name = f"audio/{uuid4().hex}.{selected_format}"
    path = default_storage.save(file_name, ContentFile(audio_bytes))

    domain = settings.DOMAIN_NAME
    if not domain.startswith("http"):
        domain = f"http://{domain}"
    return f"{domain}{settings.MEDIA_URL}{path}"


def _synthesize_openai_speech(
    *,
    text: str,
    voice: str,
    model: str,
    audio_format: str,
) -> bytes:
    client = OpenAI(api_key=_get_openai_key())
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format=audio_format,
    )
    return response.read()


def _synthesize_fish_speech(
    *,
    text: str,
    voice: str | None,
    model: str,
    audio_format: str,
) -> bytes:
    api_key = str(getattr(settings, "FISH_API_KEY", "") or "").strip()
    if not api_key:
        raise ServiceConfigurationError(
            "TTS requires FISH_API_KEY when TTS_PROVIDER=fish.",
            code="TTS_API_KEY_MISSING",
        )

    payload = {
        "text": text,
        "format": audio_format,
    }
    reference_id = _select_fish_reference_id(voice)
    if reference_id:
        payload["reference_id"] = reference_id

    connect_timeout, read_timeout = tts_provider_timeouts("fish")

    def _call() -> bytes:
        response = requests.post(
            "https://api.fish.audio/v1/tts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "model": model,
            },
            json=payload,
            timeout=(connect_timeout, read_timeout),
        )
        response.raise_for_status()
        return response.content

    return _retry_tts_call(
        _call,
        retry_on=(
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
        provider="fish",
    )


def _synthesize_elevenlabs_speech(
    *,
    text: str,
    voice: str | None,
    model: str,
    output_format: str,
) -> bytes:
    api_key = str(getattr(settings, "ELEVENLABS_API_KEY", "") or "").strip()
    if not api_key:
        raise ServiceConfigurationError(
            "TTS requires ELEVENLABS_API_KEY when TTS_PROVIDER=elevenlabs.",
            code="TTS_API_KEY_MISSING",
        )

    voice_id = _select_elevenlabs_voice_id(voice)
    if not voice_id:
        raise ServiceConfigurationError(
            "TTS requires a voice_id when TTS_PROVIDER=elevenlabs.",
            code="TTS_VOICE_ID_MISSING",
        )

    connect_timeout, read_timeout = tts_provider_timeouts("elevenlabs")
    request_timeout = connect_timeout + read_timeout

    import httpx
    from elevenlabs.client import ElevenLabs

    def _call() -> bytes:
        client = ElevenLabs(api_key=api_key, timeout=request_timeout)
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model,
            output_format=output_format,
        )
        if isinstance(audio, (bytes, bytearray)):
            return bytes(audio)
        return b"".join(chunk for chunk in audio)

    return _retry_tts_call(
        _call,
        retry_on=(
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.TimeoutException,
        ),
        provider="elevenlabs",
    )


def _select_fish_reference_id(voice: str | None) -> str:
    configured = str(getattr(settings, "FISH_TTS_REFERENCE_ID", "") or "").strip()
    requested = str(voice or "").strip()
    if requested and requested.lower() not in OPENAI_BUILTIN_VOICES:
        return requested
    return configured


def _select_elevenlabs_voice_id(voice: str | None) -> str:
    configured = str(getattr(settings, "ELEVENLABS_DEFAULT_VOICE_ID", "") or "").strip()
    requested = str(voice or "").strip()
    if requested and requested.lower() not in OPENAI_BUILTIN_VOICES:
        return requested
    return configured

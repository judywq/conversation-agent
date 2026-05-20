from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.test import override_settings

from backend.conversation.exceptions import ServiceConfigurationError
from backend.conversation.services.tts import synthesize_speech


@override_settings(
    TTS_PROVIDER="fish",
    FISH_API_KEY="fish-test-key",
    FISH_TTS_MODEL="s2-pro",
    FISH_TTS_REFERENCE_ID="8ef4a238714b45718ce04243307c57a7",
    FISH_TTS_FORMAT="mp3",
    FISH_TTS_TIMEOUT_SEC=12.0,
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_uses_fish_audio_when_configured() -> None:
    response = Mock()
    response.content = b"mp3-bytes"
    response.raise_for_status.return_value = None

    with (
        patch("backend.conversation.services.tts.requests.post", return_value=response) as post,
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3") as save,
    ):
        audio_url = synthesize_speech(text="[excited] Hello from Fish.", voice="alloy")

    post.assert_called_once_with(
        "https://api.fish.audio/v1/tts",
        headers={
            "Authorization": "Bearer fish-test-key",
            "Content-Type": "application/json",
            "model": "s2-pro",
        },
        json={
            "text": "[excited] Hello from Fish.",
            "format": "mp3",
            "reference_id": "8ef4a238714b45718ce04243307c57a7",
        },
        timeout=12.0,
    )
    save.assert_called_once()
    assert audio_url == "http://example.test/media/audio/test.mp3"


@override_settings(
    TTS_PROVIDER="fish",
    FISH_API_KEY="",
    FISH_TTS_FORMAT="mp3",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_requires_fish_api_key() -> None:
    with pytest.raises(ServiceConfigurationError, match="FISH_API_KEY"):
        synthesize_speech(text="hello")


@override_settings(
    TTS_PROVIDER="fish",
    FISH_API_KEY="fish-test-key",
    FISH_TTS_MODEL="s2-pro",
    FISH_TTS_REFERENCE_ID="",
    FISH_TTS_FORMAT="mp3",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_treats_non_openai_voice_as_fish_reference_id() -> None:
    response = Mock()
    response.content = b"mp3-bytes"
    response.raise_for_status.return_value = None

    with (
        patch("backend.conversation.services.tts.requests.post", return_value=response) as post,
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3"),
    ):
        synthesize_speech(text="hello", voice="802e3bc2b27e49c2995d23ef70e6ac89")

    assert post.call_args.kwargs["json"]["reference_id"] == "802e3bc2b27e49c2995d23ef70e6ac89"

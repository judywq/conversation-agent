from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.test import override_settings

from backend.conversation.exceptions import ServiceConfigurationError
from backend.conversation.services.tts import synthesize_speech
from backend.conversation.services.tts import synthesize_speech_with_lipsync


@override_settings(
    DEBUG=True,
    TTS_PROVIDER="fish",
    FISH_API_KEY="fish-test-key",
    FISH_TTS_MODEL="s2-pro",
    FISH_TTS_REFERENCE_ID="8ef4a238714b45718ce04243307c57a7",
    FISH_TTS_FORMAT="mp3",
    FISH_TTS_CONNECT_TIMEOUT_SEC=10.0,
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
        timeout=(10.0, 12.0),
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


@override_settings(
    DEBUG=True,
    TTS_PROVIDER="elevenlabs",
    ELEVENLABS_API_KEY="eleven-test-key",
    ELEVENLABS_MODEL_ID="eleven_v3",
    ELEVENLABS_OUTPUT_FORMAT="mp3_44100_128",
    ELEVENLABS_DEFAULT_VOICE_ID="",
    ELEVENLABS_TTS_CONNECT_TIMEOUT_SEC=10.0,
    ELEVENLABS_TTS_TIMEOUT_SEC=30.0,
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_uses_elevenlabs_when_configured() -> None:
    mock_client = Mock()
    mock_client.text_to_speech.convert.return_value = b"mp3-bytes"

    with (
        patch("elevenlabs.client.ElevenLabs", return_value=mock_client) as client_cls,
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3") as save,
    ):
        audio_url = synthesize_speech(
            text="Hello from ElevenLabs.",
            voice="scOwDtmlUjD3prqpp97I",
        )

    client_cls.assert_called_once_with(api_key="eleven-test-key", timeout=40.0)
    mock_client.text_to_speech.convert.assert_called_once_with(
        text="Hello from ElevenLabs.",
        voice_id="scOwDtmlUjD3prqpp97I",
        model_id="eleven_v3",
        output_format="mp3_44100_128",
    )
    save.assert_called_once()
    assert audio_url == "http://example.test/media/audio/test.mp3"


@override_settings(
    TTS_PROVIDER="elevenlabs",
    ELEVENLABS_API_KEY="",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_requires_elevenlabs_api_key() -> None:
    with pytest.raises(ServiceConfigurationError, match="ELEVENLABS_API_KEY"):
        synthesize_speech(text="hello", voice="scOwDtmlUjD3prqpp97I")


@override_settings(
    TTS_PROVIDER="elevenlabs",
    ELEVENLABS_API_KEY="eleven-test-key",
    ELEVENLABS_DEFAULT_VOICE_ID="",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_elevenlabs_uses_default_voice_id_when_voice_is_openai_name() -> None:
    mock_client = Mock()
    mock_client.text_to_speech.convert.return_value = b"mp3-bytes"

    with (
        patch("elevenlabs.client.ElevenLabs", return_value=mock_client),
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3"),
    ):
        with pytest.raises(ServiceConfigurationError, match="voice_id"):
            synthesize_speech(text="hello", voice="alloy")


@override_settings(
    TTS_PROVIDER="elevenlabs",
    ELEVENLABS_API_KEY="eleven-test-key",
    ELEVENLABS_DEFAULT_VOICE_ID="BIvP0GN1cAtSRTxNHnWS",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_elevenlabs_falls_back_to_default_voice_id() -> None:
    mock_client = Mock()
    mock_client.text_to_speech.convert.return_value = b"mp3-bytes"

    with (
        patch("elevenlabs.client.ElevenLabs", return_value=mock_client),
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3"),
    ):
        synthesize_speech(text="hello", voice="alloy")

    assert (
        mock_client.text_to_speech.convert.call_args.kwargs["voice_id"]
        == "BIvP0GN1cAtSRTxNHnWS"
    )


@override_settings(
    DEBUG=True,
    TTS_PROVIDER="openai",
    OPENAI_TTS_VOICE="alloy",
    OPENAI_TTS_MODEL="gpt-4o-mini-tts",
    DOMAIN_NAME="example.test",
    MEDIA_URL="/media/",
)
def test_synthesize_speech_with_lipsync_openai_returns_proportional_timings() -> None:
    mock_response = Mock()
    mock_response.read.return_value = b"\x00" * 32000

    with (
        patch("backend.conversation.services.tts.OpenAI") as openai_cls,
        patch("backend.conversation.services.tts.default_storage.save", return_value="audio/test.mp3"),
        patch("backend.conversation.services.tts.audio_duration_ms", return_value=2000),
    ):
        openai_cls.return_value.audio.speech.create.return_value = mock_response
        result = synthesize_speech_with_lipsync(text="Hello world", voice="alloy")

    assert result.audio_url == "http://example.test/media/audio/test.mp3"
    assert result.lipsync["words"] == ["Hello", "world"]
    assert result.lipsync["wtimes"] == [0, 1000]
    assert result.lipsync["wdurations"] == [1000, 1000]


from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from backend.conversation.services.stt import transcribe_audio_file


def test_transcribe_audio_file_passes_english_language_by_default():
    audio = SimpleUploadedFile("clip.webm", b"fake-audio", content_type="audio/webm")
    with (
        patch("backend.conversation.services.stt._get_openai_key", return_value="test-key"),
        patch("backend.conversation.services.stt.OpenAI") as mock_openai,
    ):
        mock_client = mock_openai.return_value
        mock_client.audio.transcriptions.create.return_value = SimpleNamespace(text=" hello ")

        text = transcribe_audio_file(audio)

    assert text == "hello"
    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["language"] == "en"
    assert kwargs["model"] == "whisper-1"
    assert kwargs["file"][0] == "clip.webm"


@override_settings(CONVERSATION_STT_LANGUAGE="")
def test_transcribe_audio_file_omits_language_when_unset():
    audio = BytesIO(b"fake-audio")
    audio.name = "clip.webm"
    with (
        patch("backend.conversation.services.stt._get_openai_key", return_value="test-key"),
        patch("backend.conversation.services.stt.OpenAI") as mock_openai,
    ):
        mock_client = mock_openai.return_value
        mock_client.audio.transcriptions.create.return_value = SimpleNamespace(text="hi")

        transcribe_audio_file(audio)

    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert "language" not in kwargs

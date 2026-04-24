from openai import OpenAI

from backend.llm_caller.models import APIKey


def _get_openai_key() -> str:
    key_obj = APIKey.objects.filter(is_active=True, llm_type="openai").order_by("order").first()
    if key_obj and key_obj.key:
        return key_obj.key
    # Fallback: some setups may only associate keys with models
    key_obj = APIKey.objects.filter(is_active=True, llm_model__llm_type="openai").order_by("order").first()
    if key_obj and key_obj.key:
        return key_obj.key
    raise RuntimeError("No active OpenAI API key configured")


def _as_openai_file_tuple(file_obj) -> tuple[str, bytes, str]:
    """
    Convert a Django UploadedFile (or file-like) into the tuple format the OpenAI
    SDK accepts for file uploads: (filename, content_bytes, content_type).
    """
    filename = getattr(file_obj, "name", None) or "audio"
    content_type = getattr(file_obj, "content_type", None) or "application/octet-stream"

    # Django UploadedFile exposes the underlying stream as `.file`
    stream = getattr(file_obj, "file", file_obj)
    if hasattr(stream, "seek"):
        try:
            stream.seek(0)
        except Exception:
            pass

    data = stream.read() if hasattr(stream, "read") else file_obj.read()
    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError(f"Expected audio bytes but received {type(data)!r}")
    return (str(filename), bytes(data), str(content_type))


def transcribe_audio_file(file_obj, *, model: str = "whisper-1") -> str:
    """
    `file_obj` should be a Django UploadedFile (or file-like) with a `.name`.
    """
    client = OpenAI(api_key=_get_openai_key())
    result = client.audio.transcriptions.create(
        model=model,
        file=_as_openai_file_tuple(file_obj),
    )
    # openai-python returns a typed object with `.text`
    return str(getattr(result, "text", "")).strip()


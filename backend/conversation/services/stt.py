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


def transcribe_audio_file(file_obj, *, model: str = "whisper-1") -> str:
    """
    `file_obj` should be a Django UploadedFile (or file-like) with a `.name`.
    """
    client = OpenAI(api_key=_get_openai_key())
    result = client.audio.transcriptions.create(
        model=model,
        file=file_obj,
    )
    # openai-python returns a typed object with `.text`
    return str(getattr(result, "text", "")).strip()


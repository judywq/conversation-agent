import json
import time
from unittest.mock import patch

from langchain_core.messages import AIMessage

from backend.conversation.services.profile_audio import generate_cefr_topic_samples


def test_generate_cefr_topic_samples_synthesizes_tts_in_parallel() -> None:
    llm_payload = {
        "samples": [
            {"level": level, "text": f"Sample text for {level}."}
            for level in ("A1", "A2", "B1", "B2", "C1", "C2")
        ],
    }

    def slow_synthesize(*, text: str, voice: str = "alloy", **kwargs) -> str:
        time.sleep(0.15)
        return f"https://example.com/{voice}/{text[:8]}.mp3"

    with (
        patch(
            "backend.conversation.services.profile_audio.get_default_chat_llm",
        ) as get_llm,
        patch(
            "backend.conversation.services.profile_audio.synthesize_speech",
            side_effect=slow_synthesize,
        ),
    ):
        get_llm.return_value.invoke.return_value = AIMessage(content=json.dumps(llm_payload))

        start = time.perf_counter()
        samples = generate_cefr_topic_samples(topic="climate change")
        elapsed = time.perf_counter() - start

    assert len(samples) == 6
    assert [s["level"] for s in samples] == ["A1", "A2", "B1", "B2", "C1", "C2"]
    assert all(s["audio_url"] for s in samples)
    # Serial would be ~0.9s; parallel should finish near one sleep plus overhead.
    assert elapsed < 0.75

from backend.conversation.services.lipsync import (
    lipsync_from_elevenlabs_alignment,
    proportional_lipsync,
    strip_audio_tags,
    tokenize_alignment_words,
)


def test_strip_audio_tags_removes_bracketed_tags():
    assert strip_audio_tags("[reflective] Hello there.") == "Hello there."


def test_tokenize_alignment_words():
    assert tokenize_alignment_words("[quietly] Hello world!") == ["Hello", "world!"]


def test_proportional_lipsync_distributes_duration_by_weight():
    result = proportional_lipsync("one two three", 3000)
    assert result.words == ["one", "two", "three"]
    assert result.wtimes == [0, 818, 1636]
    assert result.wdurations == [818, 818, 1364]
    assert sum(result.wdurations) == 3000


def test_proportional_lipsync_empty_text():
    result = proportional_lipsync("", 1000)
    assert result.words == []
    assert result.wtimes == []
    assert result.wdurations == []


def test_lipsync_from_elevenlabs_alignment_maps_words():
    alignment = {
        "characters": list("Hello world"),
        "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
    }
    result = lipsync_from_elevenlabs_alignment("Hello world", alignment)
    assert result.words == ["Hello", "world"]
    assert result.wtimes[0] == 0
    assert result.wdurations[0] >= 1
    assert result.wdurations[1] >= 1

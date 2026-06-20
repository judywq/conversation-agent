import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

_AUDIO_TAG_PATTERN = re.compile(r"\[[^\]]+\]")
_WORD_PATTERN = re.compile(r"\S+")


@dataclass(frozen=True)
class LipSyncData:
    words: list[str]
    wtimes: list[int]
    wdurations: list[int]

    def as_dict(self) -> dict[str, list[str] | list[int]]:
        return {
            "words": self.words,
            "wtimes": self.wtimes,
            "wdurations": self.wdurations,
        }


def strip_audio_tags(text: str) -> str:
    cleaned = _AUDIO_TAG_PATTERN.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize_alignment_words(text: str) -> list[str]:
    return _WORD_PATTERN.findall(strip_audio_tags(text))


def proportional_lipsync(text: str, duration_ms: int) -> LipSyncData:
    words = tokenize_alignment_words(text)
    if not words or duration_ms <= 0:
        return LipSyncData(words=[], wtimes=[], wdurations=[])

    weights = [max(len(word), 1) for word in words]
    total_weight = sum(weights)
    wtimes: list[int] = []
    wdurations: list[int] = []
    cursor = 0

    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            duration = max(duration_ms - cursor, 1)
        else:
            duration = max(int(round(duration_ms * weight / total_weight)), 1)
        wtimes.append(cursor)
        wdurations.append(duration)
        cursor += duration

    if cursor != duration_ms and wdurations:
        wdurations[-1] = max(wdurations[-1] + (duration_ms - cursor), 1)

    return LipSyncData(words=words, wtimes=wtimes, wdurations=wdurations)


def lipsync_from_elevenlabs_alignment(text: str, alignment: dict[str, Any]) -> LipSyncData:
    characters = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not characters or len(characters) != len(starts) or len(characters) != len(ends):
        duration_ms = int(float(ends[-1]) * 1000) if ends else 0
        return proportional_lipsync(text, duration_ms)

    words = tokenize_alignment_words(text)
    if not words:
        return LipSyncData(words=[], wtimes=[], wdurations=[])

    joined = "".join(characters)
    search_from = 0
    wtimes: list[int] = []
    wdurations: list[int] = []

    for word in words:
        idx = joined.find(word, search_from)
        if idx < 0:
            logger.debug("elevenlabs_alignment_word_miss word=%s", word)
            continue
        end_idx = idx + len(word) - 1
        start_ms = int(float(starts[idx]) * 1000)
        end_ms = int(float(ends[end_idx]) * 1000)
        wtimes.append(start_ms)
        wdurations.append(max(end_ms - start_ms, 1))
        search_from = end_idx + 1

    if not wtimes:
        duration_ms = int(float(ends[-1]) * 1000) if ends else 0
        return proportional_lipsync(text, duration_ms)

    return LipSyncData(words=words[: len(wtimes)], wtimes=wtimes, wdurations=wdurations)


def audio_duration_ms(audio_bytes: bytes, audio_format: str) -> int:
    fmt = (audio_format or "").lower()
    if fmt == "wav":
        return _wav_duration_ms(audio_bytes)
    if fmt in {"mp3", "mpeg"}:
        return _mp3_duration_ms(audio_bytes)
    return _fallback_duration_ms(audio_bytes, fmt)


def _wav_duration_ms(audio_bytes: bytes) -> int:
    import wave

    with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate() or 1
        return int(frames * 1000 / rate)


def _mp3_duration_ms(audio_bytes: bytes) -> int:
    try:
        from mutagen.mp3 import MP3

        return int(MP3(BytesIO(audio_bytes)).info.length * 1000)
    except Exception:
        logger.debug("mp3_duration_fallback bytes=%d", len(audio_bytes))
        return _fallback_duration_ms(audio_bytes, "mp3")


def _fallback_duration_ms(audio_bytes: bytes, audio_format: str) -> int:
    # Rough estimate when metadata parsing is unavailable.
    if audio_format == "mp3":
        bitrate_bps = 128_000
        return max(int(len(audio_bytes) * 8 * 1000 / bitrate_bps), 1)
    return max(int(len(audio_bytes) / 32), 1)

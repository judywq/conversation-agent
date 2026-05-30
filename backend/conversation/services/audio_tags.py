from __future__ import annotations

import re

from django.conf import settings


_ELEVENLABS_TAGS: dict[str, tuple[str, ...]] = {
    "Narrator Point of View": (
        "dramatic tone", "wistful", "serious tone", "matter-of-fact",
        "sarcastic tone", "awe", "lighthearted", "reflective",
    ),
    "Emotional State": (
        "sad", "angry", "happily", "sorrowful", "excited", "nervous",
        "frustrated", "tired", "calm", "cheerfully", "flatly", "deadpan",
        "playfully", "annoyed", "flustered", "casual", "pauses", "hesitates",
        "stammers", "repeats", "resigned tone", "deliberate",
    ),
    "Delivery Control": (
        "pause", "continues after a beat", "continues softly", "rushed",
        "slows down", "rapid-fire", "drawn out", "timidly", "emphasized",
        "stress on next word", "understated",
    ),
    "Human Reactions and Non-Verbal": (
        "laughs", "laughs softly", "giggle", "laughs harder", "laughing",
        "light chuckle", "big laugh", "laughs hard", "sigh", "sighing",
        "sigh of relief", "gulps", "gasps", "clears throat", "breathes",
        "whispering", "whispers", "quietly", "loudly", "shouts", "shouting",
        "clapping",
    ),
}


_FISH_TAGS: dict[str, tuple[str, ...]] = {
    "Basic Emotions": (
        "happy", "sad", "angry", "excited", "calm", "nervous",
        "confident", "surprised", "satisfied", "delighted",
        "scared", "worried", "upset", "frustrated", "depressed",
        "empathetic", "embarrassed", "disgusted", "moved", "proud",
        "relaxed", "grateful", "curious", "sarcastic",
    ),
    "Advanced Emotions": (
        "disdainful", "unhappy", "anxious", "hysterical", "indifferent",
        "uncertain", "doubtful", "confused", "disappointed", "regretful",
        "guilty", "ashamed", "jealous", "envious", "hopeful",
        "optimistic", "pessimistic", "nostalgic", "lonely", "bored",
        "contemptuous", "sympathetic", "compassionate", "determined", "resigned",
    ),
    "Tone Markers": (
        "in a hurry tone", "shouting", "screaming", "whispering", "soft tone",
    ),
}


AUDIO_TAGS_BY_PROVIDER: dict[str, dict[str, tuple[str, ...]]] = {
    "elevenlabs": _ELEVENLABS_TAGS,
    "fish": _FISH_TAGS,
}


def _resolve_provider(provider: str | None) -> str:
    selected = str(
        provider
        if provider is not None
        else getattr(settings, "TTS_PROVIDER", "elevenlabs") or "elevenlabs"
    ).lower()
    return selected if selected in AUDIO_TAGS_BY_PROVIDER else "elevenlabs"


def audio_tags_by_category(provider: str | None = None) -> dict[str, tuple[str, ...]]:
    return AUDIO_TAGS_BY_PROVIDER[_resolve_provider(provider)]


def audio_tag_allowlist(provider: str | None = None) -> frozenset[str]:
    return frozenset(
        tag for tags in audio_tags_by_category(provider).values() for tag in tags
    )


def format_audio_tags_for_prompt(provider: str | None = None) -> str:
    lines: list[str] = []
    for category, tags in audio_tags_by_category(provider).items():
        lines.append(f"{category}:")
        lines.append("  " + ", ".join(f"[{t}]" for t in tags))
    return "\n".join(lines)


_BRACKET_PATTERN = re.compile(r"\[([^\[\]]*)\]")
_PAREN_PATTERN = re.compile(r"\([^()]*\)")


def _collapse_whitespace(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text).strip()
    return re.sub(r"\s+([,.!?])", r"\1", text)


def filter_to_valid_audio_tags(text: str, provider: str | None = None) -> str:
    """
    Keep only `[tag]` occurrences whose inner text is in the active provider's
    allowlist; drop any other bracketed content and all parenthetical content.
    Used to build the string passed to the TTS provider.
    """
    if not text:
        return ""

    allowlist = audio_tag_allowlist(provider)

    def _replace(match: re.Match[str]) -> str:
        inner = match.group(1).strip().lower()
        if inner in allowlist:
            return f"[{inner}]"
        return ""

    cleaned = _BRACKET_PATTERN.sub(_replace, text)
    cleaned = _PAREN_PATTERN.sub("", cleaned)
    return _collapse_whitespace(cleaned)


def strip_audio_tags(text: str) -> str:
    """
    Remove all bracketed and parenthetical content. Used to build the
    string persisted to the turn record and shown in the UI.
    Provider-agnostic.
    """
    if not text:
        return ""
    cleaned = _BRACKET_PATTERN.sub("", text)
    cleaned = _PAREN_PATTERN.sub("", cleaned)
    return _collapse_whitespace(cleaned)

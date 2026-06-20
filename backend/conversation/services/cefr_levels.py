from __future__ import annotations

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
DEFAULT_CEFR_LEVEL = "B1"


def normalize_user_cefr_level(level: str | None) -> str:
    normalized = str(level or "").upper().strip()
    if normalized in CEFR_LEVELS:
        return normalized
    return DEFAULT_CEFR_LEVEL

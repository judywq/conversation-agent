#!/usr/bin/env python3
"""
Generate Fish Audio TTS samples for five male and five female named voices.

Usage:
    export FISH_API_KEY="..."
    python xmtest/test_fish_audio_10_voices.py

Optional:
    FISH_TTS_MODEL=s2-pro python xmtest/test_fish_audio_10_voices.py --text "Hello!"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


API_URL = "https://api.fish.audio/v1/tts"
DEFAULT_MODEL = os.getenv("FISH_TTS_MODEL", "s2-pro")
DEFAULT_FORMAT = os.getenv("FISH_TTS_FORMAT", "mp3")
OUTPUT_DIR = Path(__file__).resolve().parent / "fish_voice_samples"


@dataclass(frozen=True)
class Voice:
    name: str
    chinese_name: str
    gender: str
    title: str
    reference_id: str
    note: str


VOICES = [
    Voice(
        name="Liam",
        chinese_name="利亚姆",
        gender="male",
        title="Energetic Male",
        reference_id="802e3bc2b27e49c2995d23ef70e6ac89",
        note="young, clear, energetic English male voice",
    ),
    Voice(
        name="Ethan",
        chinese_name="伊森",
        gender="male",
        title="ELITE",
        reference_id="d8a1340984ee4b63ad1ffae27a6a4339",
        note="confident sports-commentary style English male voice",
    ),
    Voice(
        name="Noah",
        chinese_name="诺亚",
        gender="male",
        title="ALEX_CHIKNA",
        reference_id="52e0660e03fe4f9a8d2336f67cab5440",
        note="fast, enthusiastic English male voice",
    ),
    Voice(
        name="Oliver",
        chinese_name="奥利弗",
        gender="male",
        title="id-alex",
        reference_id="1d52151a55eb4878a997bd06e816b5f6",
        note="A professional and calm middle-aged male voice with a clear, articulate delivery. This voice features a smooth, medium-pitched tone, making it well-suited for storytelling and narration.",
    ),
    Voice(
        name="Lucas",
        chinese_name="卢卡斯",
        gender="male",
        title="id-Ethan",
        reference_id="536d3a5e000945adb7038665781a4aca",
        note="deep, cinematic character-style English male voice",
    ),
    Voice(
        name="Emma",
        chinese_name="艾玛",
        gender="female",
        title="id-ss",
        reference_id="1954744f560e4a0fa316bd6ec8a6b055",
        note="A cute e-girl to chat with you.",
    ),
    Voice(
        name="Sophia",
        chinese_name="索菲亚",
        gender="female",
        title="id-Paula",
        reference_id="c2623f0c075b4492ac367989aee1576f",
        note="A professional and clear female voice with a middle-aged tone. This voice is ideal for educational content and professional presentations, characterized by its confident and friendly delivery.",
    ),
    Voice(
        name="Ava",
        chinese_name="艾娃",
        gender="female",
        title="id-Friendly Women",
        reference_id="b545c585f631496c914815291da4e893",
        note="A bright and energetic female voice with a youthful, professional tone. Her delivery is clear and enthusiastic, making it highly engaging for a variety of media.",
    ),
    Voice(
        name="Isabella",
        chinese_name="伊莎贝拉",
        gender="female",
        title="id-Ogechi old women",
        reference_id="edb42faa2d0e4cd5aa6aa1ae67de2e86",
        note="cute character-style female voice",
    ),
    Voice(
        name="Mia",
        chinese_name="米娅",
        gender="female",
        title="id-Female Voice",
        reference_id="2a9605eeafe84974b5b20628d42c0060",
        note="A young female voice with a calm, reflective tone and a smooth, measured pace. She sounds thoughtful and authentic, making this voice suitable for personal narratives or social media content.",
    ),
]


def build_text(voice: Voice, custom_text: str | None) -> str:
    if custom_text:
        return custom_text.format(
            name=voice.name,
            chinese_name=voice.chinese_name,
            gender=voice.gender,
            title=voice.title,
        )
    return (
        f"Hello, my name is {voice.name}. "
        "This is a Fish Audio voice test for a conversation agent. "
        "I will read clearly, naturally, and with a friendly tone."
    )


def slugify_file_part(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "voice"


def synthesize_voice(
    *,
    api_key: str,
    model: str,
    audio_format: str,
    voice: Voice,
    text: str,
    timeout: float,
) -> bytes:
    payload = {
        "text": text,
        "reference_id": voice.reference_id,
        "format": audio_format,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": model,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Fish Audio HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Fish Audio request failed: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test 10 selected Fish Audio voices.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Fish model header, default: %(default)s")
    parser.add_argument("--format", default=DEFAULT_FORMAT, help="Audio format, default: %(default)s")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory for generated audio files")
    parser.add_argument("--timeout", type=float, default=90.0, help="Request timeout seconds")
    parser.add_argument("--sleep", type=float, default=0.8, help="Delay between requests to reduce rate limiting")
    parser.add_argument(
        "--text",
        default=None,
        help=(
            "Custom text. You can use {name}, {chinese_name}, {gender}, and {title} placeholders."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print selected voices without calling the API")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("FISH_API_KEY", "").strip()

    print("Selected voices:")
    for index, voice in enumerate(VOICES, start=1):
        print(
            f"{index:02d}. {voice.name} ({voice.chinese_name}) | "
            f"{voice.gender} | {voice.title} | {voice.reference_id} | {voice.note}"
        )

    if args.dry_run:
        return 0

    if not api_key:
        raise SystemExit("Missing FISH_API_KEY. Run: export FISH_API_KEY='your_api_key'")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, voice in enumerate(VOICES, start=1):
        text = build_text(voice, args.text)
        file_name = (
            f"{index:02d}_{voice.gender}_{slugify_file_part(voice.name)}_"
            f"{slugify_file_part(voice.title)}.{args.format}"
        )
        output_path = output_dir / file_name
        print(f"Generating {output_path.name} ...")
        audio = synthesize_voice(
            api_key=api_key,
            model=args.model,
            audio_format=args.format,
            voice=voice,
            text=text,
            timeout=args.timeout,
        )
        output_path.write_bytes(audio)
        time.sleep(args.sleep)

    print(f"Done. Audio files saved in: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# export FISH_API_KEY="f261d7e683a94228845620f17997ba66"

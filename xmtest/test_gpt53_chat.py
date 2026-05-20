#!/usr/bin/env python3
"""
Test whether gpt-5.3-chat-latest (INIT_LLM_MODELS default in config/settings/base.py) is callable.

Usage (recommended — key stays in your shell, not in shell history if you use env file):
  export OPENAI_API_KEY='sk-...'
  python scripts/test_gpt53_chat.py

Or pass key as first argument (less safe):
  python scripts/test_gpt53_chat.py 'sk-...'
"""

from __future__ import annotations

import os
import sys

MODEL = "gpt-5.3-chat-latest"
TEST_PROMPT = "read a happy story about a cat"


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key and len(sys.argv) > 1:
        api_key = sys.argv[1].strip()
    if not api_key:
        print("Missing API key.")
        print("  export OPENAI_API_KEY='sk-...'")
        print("  python scripts/test_gpt53_chat.py")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("Install openai: pip install openai")
        return 1

    client = OpenAI(api_key=api_key)
    print(f"Calling model: {MODEL}")
    print(f"Prompt: {TEST_PROMPT!r}")
    print("-" * 40)

    try:
        # gpt-5.x may consume completion budget on internal reasoning; keep headroom.
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": TEST_PROMPT}],
            # max_completion_tokens=512,
        )
    except Exception as exc:
        print("FAILED")
        print(f"  {type(exc).__name__}: {exc}")
        return 1

    choice = response.choices[0]
    text = choice.message.content if choice.message else ""
    print("SUCCESS")
    print(f"  finish_reason: {choice.finish_reason}")
    print(f"  content: {text!r}")
    if response.usage:
        print(
            "  usage: "
            f"prompt={response.usage.prompt_tokens} "
            f"completion={response.usage.completion_tokens} "
            f"total={response.usage.total_tokens}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

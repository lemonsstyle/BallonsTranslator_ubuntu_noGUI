#!/usr/bin/env python
"""Minimal OpenRouter connectivity + translation smoke test.

Edit the USER_* values below, then run:
    conda activate pc
    python scripts/openrouter_smoketest.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

import requests


# ---------------------------------------------------------------------------
# Fill these values directly for a quick manual test.
# ---------------------------------------------------------------------------
USER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
USER_API_KEY = "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"
USER_MODEL = "deepseek/deepseek-chat-v3-0324"
USER_PROMPT = "Translate the input text into Simplified Chinese. Return only the translated text."
USER_TEXT = "こんにちは。"


def normalize_chat_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return endpoint + "/chat/completions"


def build_payload(model: str, prompt: str, text: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenRouter translation smoke test")
    parser.add_argument("--endpoint", default=USER_ENDPOINT)
    parser.add_argument("--api-key", default=USER_API_KEY)
    parser.add_argument("--model", default=USER_MODEL)
    parser.add_argument("--prompt", default=USER_PROMPT)
    parser.add_argument("--text", default=USER_TEXT)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: API key is empty.")
        print("Set USER_API_KEY in this file, or export OPENROUTER_API_KEY, or pass --api-key.")
        return 2

    endpoint = normalize_chat_endpoint(args.endpoint)
    payload = build_payload(
        model=args.model,
        prompt=args.prompt,
        text=args.text,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "BallonsTranslator OpenRouter Smoke Test",
    }

    print(f"POST {endpoint}")
    print(f"model={args.model}")
    print(f"text={args.text}")

    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=args.timeout,
        )
    except requests.RequestException as exc:
        print(f"REQUEST ERROR: {exc}")
        return 1

    print(f"HTTP {resp.status_code}")

    if resp.status_code >= 400:
        print("ERROR BODY:")
        print(resp.text)
        return 1

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("ERROR: response is not valid JSON")
        print(resp.text)
        return 1

    try:
        translated = data["choices"][0]["message"]["content"]
    except Exception:
        print("ERROR: unexpected response schema")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 1

    print("\n=== TRANSLATION RESULT ===")
    print(translated)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Probe which models this key can actually call.

    python scripts/probe_models.py [--limit N]

Sends a one-token completion to every model the gateway lists and prints the
HTTP status plus the error type. One token per model keeps the probe free, and
running it over the whole list is what distinguishes "the key is wrong" from
"this particular model is not covered by the subscription".
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("LLM_BASE_URL", "https://opencode.ai/zen/v1").rstrip("/")


def _key() -> str:
    key = (os.environ.get("LLM_API_KEY", "") or "").strip()
    if not key and os.path.exists(".env"):
        for line in open(".env", encoding="utf-8-sig"):
            if line.startswith("LLM_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("LLM_API_KEY not found in env or .env")
    return key


def _headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Cloudflare in front of the gateway rejects the default urllib agent.
        "User-Agent": "ragqa-probe/0.1",
    }


def call(key: str, model: str, tokens: int = 1):
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ok"}],
            "temperature": 0,
            "max_tokens": tokens,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=payload,
        headers=_headers(key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
            usage = body.get("usage", {})
            return 200, f"in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}"
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            error = parsed.get("error", {})
            return exc.code, f"{error.get('type')}: {str(error.get('message'))[:90]}"
        except json.JSONDecodeError:
            return exc.code, raw[:90]
    except Exception as exc:  # noqa: BLE001 - network failures are data here
        return 0, str(exc)[:90]


def list_models(key: str):
    request = urllib.request.Request(f"{BASE}/models", headers=_headers(key))
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    return sorted(item["id"] for item in body.get("data", []))


def main(argv):
    key = _key()
    limit = 0
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    models = list_models(key)
    if limit:
        models = models[:limit]
    print(f"base: {BASE}  models: {len(models)}\n")
    usable = []
    for model in models:
        status, detail = call(key, model)
        flag = "OK " if status == 200 else "   "
        print(f"{flag}{status:<4} {model:<34} {detail}")
        if status == 200:
            usable.append(model)
    print(f"\nusable: {len(usable)}")
    for model in usable:
        print(f"  {model}")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

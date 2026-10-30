"""OpenAI-compatible chat client with a response cache (ticket 06).

Two things make this worth writing rather than calling out inline: every request
is cached by content hash, so a re-run of an experiment costs nothing and returns
the same text (the determinism the whole matrix depends on), and every failure is
classified instead of raised, because a 402 from the gateway and a truncated JSON
answer mean different things for the report.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional


def load_env(path: str = ".env") -> Dict[str, str]:
    values: Dict[str, str] = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class LLMError(RuntimeError):
    def __init__(self, kind: str, detail: str, status: int = 0):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail
        self.status = status


class ResponseCache:
    def __init__(self, path: str):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            " key TEXT PRIMARY KEY, model TEXT NOT NULL, text TEXT NOT NULL,"
            " tokens_in INTEGER, tokens_out INTEGER, latency_ms REAL)"
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT text, tokens_in, tokens_out, latency_ms FROM responses WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        text, tokens_in, tokens_out, latency_ms = row
        return {
            "text": text,
            "tokens_in": int(tokens_in or 0),
            "tokens_out": int(tokens_out or 0),
            "latency_ms": float(latency_ms or 0.0),
            "cached": True,
        }

    def put(self, key: str, model: str, result: Dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO responses (key, model, text, tokens_in, tokens_out, latency_ms)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                key,
                model,
                result["text"],
                result["tokens_in"],
                result["tokens_out"],
                result["latency_ms"],
            ),
        )

    def flush(self) -> None:
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0])

    def close(self) -> None:
        self.flush()
        self._conn.close()


class LLMClient:
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        cache_path: str = "data/cache/llm.sqlite",
        timeout: int = 120,
        temperature: float = 0.0,
        max_retries: int = 3,
        session_header: str = "",
        session_id: str = "",
        reasoning_effort: str = "",
    ):
        env = load_env()
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or env.get("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "") or env.get("LLM_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise LLMError(
                "config",
                "LLM_BASE_URL and LLM_API_KEY must be set in the environment or .env",
            )
        self.cache = ResponseCache(cache_path)
        self.timeout = int(timeout)
        self.temperature = float(temperature)
        self.max_retries = int(max_retries)
        # OpenCode Go routes a conversation by this header; without it the request
        # lands on the wrong catalog and fails upstream (see docs/PROGRESS.md).
        self.session_header = (session_header or "").strip()
        self.session_id = session_id or str(uuid.uuid4())
        # `reasoning_effort: none` turns off the model's thinking channel. That
        # matters for mechanical calls: at the default effort a one-sentence prefix
        # spends 163 reasoning tokens and can return empty content inside a small
        # max_tokens budget. Generation keeps the default effort.
        self.reasoning_effort = (reasoning_effort or "").strip()
        self.last_stats: Dict[str, int] = {"hits": 0, "misses": 0, "tokens_in": 0, "tokens_out": 0}

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Cloudflare in front of the gateway blocks the default urllib agent.
            "User-Agent": "ragqa/0.1",
        }
        if self.session_header:
            headers[self.session_header] = self.session_id
        return headers

    def _key(self, model: str, messages: List[Dict[str, str]], max_tokens: int, json_mode: bool) -> str:
        material = json.dumps(
            {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
                "temperature": self.temperature,
                "reasoning_effort": self.reasoning_effort,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 800,
        json_mode: bool = True,
    ) -> Dict[str, Any]:
        key = self._key(model, messages, max_tokens, json_mode)
        cached = self.cache.get(key)
        if cached is not None and cached.get("text"):
            self.last_stats["hits"] += 1
            self.last_stats["tokens_in"] += cached["tokens_in"]
            self.last_stats["tokens_out"] += cached["tokens_out"]
            return cached

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": int(max_tokens),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        attempt = 0
        while True:
            attempt += 1
            began = time.perf_counter()
            try:
                body = self._post(payload)
            except LLMError as error:
                retryable = error.status in (429, 500, 502, 503, 504)
                if retryable and attempt <= self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise
            latency_ms = (time.perf_counter() - began) * 1000.0
            choices = body.get("choices") or []
            if not choices:
                raise LLMError("empty_response", json.dumps(body)[:200])
            text = (choices[0].get("message") or {}).get("content") or ""
            usage = body.get("usage") or {}
            result = {
                "text": text,
                "tokens_in": int(usage.get("prompt_tokens") or 0),
                "tokens_out": int(usage.get("completion_tokens") or 0),
                "latency_ms": latency_ms,
                "cached": False,
            }
            self.cache.put(key, model, result)
            self.cache.flush()
            self.last_stats["misses"] += 1
            self.last_stats["tokens_in"] += result["tokens_in"]
            self.last_stats["tokens_out"] += result["tokens_out"]
            return result

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            kind = "http_error"
            detail = raw[:300]
            try:
                parsed = json.loads(raw)
                error = parsed.get("error") or {}
                kind = str(error.get("type") or kind)
                detail = str(error.get("message") or detail)
            except json.JSONDecodeError:
                pass
            raise LLMError(kind, detail, status=exc.code) from exc
        except Exception as exc:  # noqa: BLE001 - network failures are classified
            raise LLMError("transport", str(exc)[:300]) from exc

    def close(self) -> None:
        self.cache.close()

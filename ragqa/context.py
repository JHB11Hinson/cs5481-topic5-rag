"""Contextual prefixes (ticket 07, ADR-0006).

A chunk retrieved on its own is often ambiguous: "the default is false" is a true
sentence that answers nothing until a reader knows which setting, in which
document, under which heading. A contextual prefix is one generated sentence that
places the chunk in its document, prepended before indexing so both the dense
vector and the sparse term list carry that placement.

Three decisions worth stating out loud:

1. The prefix goes into the *index*, not into the generation prompt. The prompt
   keeps the original chunk text because a claim must quote the chunk verbatim
   for the verifier to locate it (`ADR-0004`); a model that quotes the prefix
   would manufacture a containment failure out of a better retrieval.
2. The cache key is `(model, prompt_version, sha256(prompt))`. A rerun therefore
   reports 100% hits and the same strings, which is what makes an A/B against the
   plain level a comparison rather than two samples.
3. Generation is per chunk: 2,203 chunks is a few minutes at 4 concurrent cheap
   calls and the cost is recorded rather than estimated.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .textutil import normalize

SYSTEM_PROMPT = (
    "You help a documentation search index. You are given one excerpt of a "
    "technical document, plus where it sits. Write ONE sentence, at most 40 "
    "words, that situates the excerpt: name the product feature or task, the "
    "page or section it belongs to, and what the excerpt is about. Do not repeat "
    "the excerpt, do not add facts that are not in the material, do not use "
    "markdown, and do not write 'this chunk' or 'this excerpt'. Reply with the "
    "sentence only."
)

MAX_EXCERPT_CHARS = 1400
MAX_NEIGHBOUR_CHARS = 500
MAX_PREFIX_CHARS = 400


def prompt_for(
    doc_id: str,
    heading_path: str,
    text: str,
    before: str = "",
    after: str = "",
) -> str:
    """The exact string hashed for the cache and sent to the model."""
    parts = [f"Document: {doc_id}"]
    if heading_path:
        parts.append(f"Section: {heading_path}")
    if before:
        parts.append("Previous excerpt:\n" + normalize(before)[:MAX_NEIGHBOUR_CHARS])
    parts.append("Excerpt:\n" + normalize(text)[:MAX_EXCERPT_CHARS])
    if after:
        parts.append("Next excerpt:\n" + normalize(after)[:MAX_NEIGHBOUR_CHARS])
    return "\n\n".join(parts)


def sanitize(prefix: str) -> str:
    """One line, no markdown furniture, bounded length."""
    text = normalize(prefix or "").strip().strip('"').strip("'")
    for marker in ("```", "**", "###"):
        text = text.replace(marker, "")
    if len(text) > MAX_PREFIX_CHARS:
        text = text[:MAX_PREFIX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return text


class PrefixCache:
    """SQLite keyed by (model, prompt_version, sha256(prompt))."""

    def __init__(self, path: str):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS prefixes ("
            " key TEXT PRIMARY KEY, model TEXT NOT NULL, prompt_version TEXT NOT NULL,"
            " prefix TEXT NOT NULL, tokens_in INTEGER, tokens_out INTEGER)"
        )
        self._conn.commit()

    @staticmethod
    def key(model: str, prompt_version: str, prompt: str) -> str:
        return hashlib.sha256(
            f"{model}|{prompt_version}|{prompt}".encode("utf-8")
        ).hexdigest()

    def get(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT prefix FROM prefixes WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, prompt_version: str, prefix: str,
            tokens_in: int, tokens_out: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO prefixes"
            " (key, model, prompt_version, prefix, tokens_in, tokens_out)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (key, model, prompt_version, prefix, int(tokens_in), int(tokens_out)),
        )

    def flush(self) -> None:
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM prefixes").fetchone()[0])

    def close(self) -> None:
        self.flush()
        self._conn.close()


class PrefixGenerator:
    """Attach a contextual prefix to every child chunk.

    `client` is anything with `.complete(model, messages, max_tokens)`; the
    default single-threaded path reuses one client, and `client_factory` (one
    client per thread, each with its own SQLite handle) is what makes the
    concurrent path safe.
    """

    def __init__(
        self,
        client,
        model: str,
        cache_path: str = "data/cache/prefixes.sqlite",
        max_tokens: int = 120,
        prompt_version: str = "v1",
        concurrency: int = 1,
        client_factory: Optional[Callable[[], Any]] = None,
    ):
        if not model:
            raise ValueError("PrefixGenerator needs a model id")
        self.model = model
        self.cache = PrefixCache(cache_path)
        self.max_tokens = int(max_tokens)
        self.prompt_version = str(prompt_version)
        self.concurrency = max(1, int(concurrency))
        self.client = client
        self.client_factory = client_factory
        self.last_stats: Dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "seconds": 0.0,
            "chunks": 0,
            "prefix_chars": [],
        }

    def _call(self, client, prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        return client.complete(self.model, messages, max_tokens=self.max_tokens)

    def generate(
        self,
        chunks: List[Dict[str, Any]],
        docs_by_id: Dict[str, Dict[str, Any]],
        neighbours: int = 1,
    ) -> Dict[str, Any]:
        began = time.perf_counter()
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in chunks:
            by_doc.setdefault(chunk["doc_id"], []).append(chunk)

        jobs: List[tuple] = []
        hits = 0
        for doc_id, doc_chunks in by_doc.items():
            doc_chunks.sort(key=lambda c: c["char_start"])
            for position, chunk in enumerate(doc_chunks):
                before = ""
                after = ""
                if neighbours:
                    if position > 0:
                        before = doc_chunks[position - 1]["text"]
                    if position + 1 < len(doc_chunks):
                        after = doc_chunks[position + 1]["text"]
                prompt = prompt_for(
                    doc_id,
                    chunk.get("heading_path", ""),
                    chunk["text"],
                    before,
                    after,
                )
                key = PrefixCache.key(self.model, self.prompt_version, prompt)
                cached = self.cache.get(key)
                if cached is not None:
                    chunk["prefix"] = cached
                    hits += 1
                    continue
                jobs.append((chunk, prompt, key))

        self.last_stats["hits"] = hits
        self.last_stats["misses"] = len(jobs)

        def run(job):
            chunk, prompt, key = job
            client = self.client
            if self.concurrency > 1 and self.client_factory is not None:
                client = self.client_factory()
            result = self._call(client, prompt)
            return chunk, key, result

        if jobs:
            if self.concurrency > 1 and self.client_factory is not None:
                with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                    for chunk, key, result in pool.map(run, jobs):
                        self._store(chunk, key, result)
            else:
                for job in jobs:
                    chunk, key, result = run(job)
                    self._store(chunk, key, result)
        self.cache.flush()

        for chunk in chunks:
            prefix = chunk.get("prefix", "")
            chunk["contextual_text"] = (prefix + "\n\n" + chunk["text"]).strip() if prefix else chunk["text"]
        self.last_stats["chunks"] = len(chunks)
        self.last_stats["seconds"] = round(time.perf_counter() - began, 3)
        return dict(self.last_stats)

    def _store(self, chunk: Dict[str, Any], key: str, result: Dict[str, Any]) -> None:
        prefix = sanitize(result.get("text", ""))
        chunk["prefix"] = prefix
        tokens_in = int(result.get("tokens_in", 0) or 0)
        tokens_out = int(result.get("tokens_out", 0) or 0)
        self.cache.put(key, self.model, self.prompt_version, prefix, tokens_in, tokens_out)
        self.last_stats["tokens_in"] += tokens_in
        self.last_stats["tokens_out"] += tokens_out
        self.last_stats["prefix_chars"].append(len(prefix))

    def summary(self) -> Dict[str, Any]:
        lengths = sorted(self.last_stats.get("prefix_chars") or [])
        p50 = lengths[len(lengths) // 2] if lengths else 0
        return {
            "model": self.model,
            "prompt_version": self.prompt_version,
            "chunks": self.last_stats.get("chunks", 0),
            "cache_hits": self.last_stats.get("hits", 0),
            "cache_misses": self.last_stats.get("misses", 0),
            "tokens_in": self.last_stats.get("tokens_in", 0),
            "tokens_out": self.last_stats.get("tokens_out", 0),
            "prefix_p50_chars": p50,
            "prefix_max_chars": lengths[-1] if lengths else 0,
            "seconds": self.last_stats.get("seconds", 0.0),
        }

    def close(self) -> None:
        self.cache.close()


def write_contextual_chunks(path: str, chunks: List[Dict[str, Any]]) -> str:
    """`chunks_contextual.jsonl`: prefix, contextual text, original text — all three."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            if chunk.get("kind") != "child":
                continue
            handle.write(
                json.dumps(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "doc_id": chunk["doc_id"],
                        "heading_path": chunk.get("heading_path", ""),
                        "prefix": chunk.get("prefix", ""),
                        "contextual_text": chunk.get("contextual_text", chunk["text"]),
                        "text": chunk["text"],
                        "char_start": chunk["char_start"],
                        "char_end": chunk["char_end"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return path

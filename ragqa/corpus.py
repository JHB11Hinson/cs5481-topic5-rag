"""Corpus loading and snapshot identity.

A snapshot is the frozen set of documents a run is measured against; every
downstream artifact carries its id so no number is unmoored from its inputs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List

from .textutil import normalize


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON ({exc})") from exc
    return records


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def load_documents(path: str) -> List[Dict[str, Any]]:
    docs = read_jsonl(path)
    if not docs:
        raise ValueError(f"{path}: corpus is empty")
    seen = set()
    for doc in docs:
        for field in ("doc_id", "text"):
            if not doc.get(field):
                raise ValueError(f"{path}: document missing {field!r}: {doc!r}")
        if doc["doc_id"] in seen:
            raise ValueError(f"{path}: duplicate doc_id {doc['doc_id']!r}")
        seen.add(doc["doc_id"])
    return docs


def snapshot_identity(docs: Iterable[Dict[str, Any]], snapshot_id: str) -> Dict[str, Any]:
    ordered = sorted(docs, key=lambda d: d["doc_id"])
    per_doc = [
        {
            "doc_id": doc["doc_id"],
            "sha256": content_hash(doc["text"]),
            "chars": len(doc["text"]),
            "url": doc.get("url", ""),
        }
        for doc in ordered
    ]
    digest = hashlib.sha256(
        "".join(f"{d['doc_id']}:{d['sha256']}" for d in per_doc).encode("utf-8")
    ).hexdigest()
    return {
        "snapshot_id": snapshot_id,
        "documents": len(per_doc),
        "chars": sum(d["chars"] for d in per_doc),
        "digest": digest,
        "docs": per_doc,
    }

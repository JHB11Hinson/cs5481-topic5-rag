"""Golden QA set loading and validation (golden/SPEC.md)."""

from __future__ import annotations

from typing import Any, Dict, List

from .corpus import read_jsonl
from .textutil import normalize

QUOTAS = {"fact_lookup": 10, "param_value": 8, "table_content": 8, "multi_hop": 8, "concept": 6}
NEGATIVE_TARGET = 20
FIELDS_ANSWERABLE = ("id", "question", "reference_answer", "evidence", "type")
FIELDS_NEGATIVE = ("id", "question", "why_unanswerable")


def load(path: str, limit: int = None) -> List[Dict[str, Any]]:
    items = read_jsonl(path)
    if limit:
        items = items[: int(limit)]
    seen = set()
    for item in items:
        if item["id"] in seen:
            raise ValueError(f"{path}: duplicate item id {item['id']!r}")
        seen.add(item["id"])
    return items


def validate(path: str, docs: List[Dict[str, Any]], strict_quotas: bool = False) -> List[str]:
    """Return a list of problems; empty means the set is usable."""
    problems: List[str] = []
    items = read_jsonl(path)
    texts = {doc["doc_id"]: normalize(doc["text"]) for doc in docs}
    ids = set()
    counts: Dict[str, int] = {}
    negatives = 0

    for item in items:
        item_id = item.get("id", "<missing id>")
        if item_id in ids:
            problems.append(f"{item_id}: duplicate id")
        ids.add(item_id)

        answerable = bool(item.get("answerable", True))
        required = FIELDS_ANSWERABLE if answerable else FIELDS_NEGATIVE
        for field in required:
            if not item.get(field):
                problems.append(f"{item_id}: missing field {field!r}")

        question = item.get("question", "")
        if not (15 <= len(question) <= 400):
            problems.append(f"{item_id}: question length {len(question)} outside [15, 400]")

        if not answerable:
            negatives += 1
            continue

        counts[item.get("type", "?")] = counts.get(item.get("type", "?"), 0) + 1
        for evidence in item.get("evidence", []):
            doc_id = evidence.get("doc_id")
            quote = normalize(evidence.get("quote", ""))
            if doc_id not in texts:
                problems.append(f"{item_id}: doc_id {doc_id!r} not in corpus")
                continue
            if not quote:
                problems.append(f"{item_id}: empty quote for {doc_id}")
                continue
            if quote not in texts[doc_id]:
                problems.append(f"{item_id}: quote not found verbatim in {doc_id}")
                continue
            occurrences = sum(t.count(quote) for t in texts.values())
            if occurrences > 1:
                problems.append(f"{item_id}: quote occurs {occurrences} times in corpus, not unique")

    if strict_quotas:
        for stratum, target in QUOTAS.items():
            if counts.get(stratum, 0) != target:
                problems.append(f"stratum {stratum}: {counts.get(stratum, 0)} items, expected {target}")
        if negatives != NEGATIVE_TARGET:
            problems.append(f"near-miss items: {negatives}, expected {NEGATIVE_TARGET}")
    return problems

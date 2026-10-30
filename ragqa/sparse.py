"""Sparse retrieval: BM25 over chunk text, implemented directly.

Exact identifiers are the weakness of dense retrieval and this corpus is full of
them — `background_pool_size`, `replication_dry_run`, endpoint paths. A lexical
branch is what makes those findable, which is why the hybrid level of the
retrieval factor exists (`ADR-0006` is about the other factor; this one is the
survey's "exact-ID misses" failure mode made concrete).

No external dependency: the scoring is a few counters, and having it in-tree
means the sparse branch can be inspected and tested rather than trusted.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence, Tuple

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


class BM25Index:
    backend = "bm25"

    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._ids: List[str] = []
        self._term_freqs: List[Counter] = []
        self._lengths: List[int] = []
        self._doc_freq: Counter = Counter()
        self._avg_length = 0.0
        self.build_seconds = 0.0

    def add(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        if len(ids) != len(texts):
            raise ValueError("ids and texts must be the same length")
        self._ids = list(ids)
        self._term_freqs = []
        self._lengths = []
        self._doc_freq = Counter()
        for text in texts:
            tokens = tokenize(text)
            counts = Counter(tokens)
            self._term_freqs.append(counts)
            self._lengths.append(len(tokens))
            for term in counts:
                self._doc_freq[term] += 1
        total = sum(self._lengths)
        self._avg_length = total / len(self._lengths) if self._lengths else 0.0

    def _idf(self, term: str) -> float:
        n = len(self._ids)
        df = self._doc_freq.get(term, 0)
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int) -> List[Tuple[str, float]]:
        if not self._ids:
            return []
        terms = tokenize(query)
        if not terms:
            return []
        scores: List[float] = [0.0] * len(self._ids)
        for term in terms:
            idf = self._idf(term)
            if idf <= 0:
                continue
            for index, counts in enumerate(self._term_freqs):
                freq = counts.get(term)
                if not freq:
                    continue
                length = self._lengths[index] or 1
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * (length / (self._avg_length or 1.0))
                )
                scores[index] += idf * (freq * (self.k1 + 1)) / denominator
        ranked = sorted(
            ((self._ids[i], score) for i, score in enumerate(scores) if score > 0),
            key=lambda pair: -pair[1],
        )
        return ranked[: max(1, k)]

    def count(self) -> int:
        return len(self._ids)

    def size_bytes(self) -> int:
        return sum(len(str(counts)) for counts in self._term_freqs) * 64

    def close(self) -> None:
        return None


def rrf_fuse(
    branches: Dict[str, List[Tuple[str, float]]], rrf_k: int = 60, limit: int = 10
) -> List[Tuple[str, float, Dict[str, int]]]:
    """Reciprocal rank fusion; returns (id, fused_score, per-branch ranks)."""
    fused: Dict[str, float] = {}
    ranks: Dict[str, Dict[str, int]] = {}
    for name, ranked in branches.items():
        for rank, (item_id, _score) in enumerate(ranked, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (rrf_k + rank)
            ranks.setdefault(item_id, {})[name] = rank
    ordered = sorted(fused.items(), key=lambda pair: -pair[1])[:limit]
    return [(item_id, score, ranks[item_id]) for item_id, score in ordered]

"""Retrieval.

Three modes, matching the three levels of the retrieval factor:

- `dense`: cosine over bge-m3 (or stub) vectors.
- `hybrid`: dense ∥ BM25, fused with RRF.
- `rerank`: hybrid candidates rescored by a cross-encoder.

Unimplemented combinations raise instead of degrading: a cell that silently
falls back to dense would make two rows of the matrix identical and nobody would
notice until the numbers were in the report.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .index import MemoryIndex
from .sparse import BM25Index, rrf_fuse

DEFAULT_RRF_K = 60


def _cross_encoder(model_id: str, max_length: int = 512):
    from sentence_transformers import CrossEncoder

    if not hasattr(_cross_encoder, "_cache"):
        _cross_encoder._cache = {}
    key = (model_id, int(max_length))
    if key not in _cross_encoder._cache:
        _cross_encoder._cache[key] = CrossEncoder(model_id, max_length=int(max_length))
    return _cross_encoder._cache[key]


def retrieve(
    index,
    chunks_by_id: Dict[str, Dict[str, Any]],
    query_vector: Sequence[float],
    mode: str,
    k: int,
    query: str = "",
    sparse: BM25Index = None,
    reranker: str = "",
    rerank_top: int = 8,
    rerank_max_length: int = 512,
    rrf_k: int = DEFAULT_RRF_K,
) -> List[Dict[str, Any]]:
    branches: Dict[str, List] = {}
    hits = index.search(query_vector, k)
    branches["dense"] = hits

    if mode in ("hybrid", "rerank"):
        if sparse is None:
            raise ValueError("hybrid retrieval needs a BM25 index")
        if not query:
            raise ValueError("hybrid retrieval needs the query text")
        branches["sparse"] = sparse.search(query, k)
        fused = rrf_fuse(branches, rrf_k=rrf_k, limit=k)
        ordered = [
            {"chunk_id": chunk_id, "score": score, "branches": ranks}
            for chunk_id, score, ranks in fused
        ]
    elif mode == "dense":
        ordered = [
            {"chunk_id": chunk_id, "score": score, "branches": {"dense": rank}}
            for rank, (chunk_id, score) in enumerate(hits, start=1)
        ]
    else:
        raise ValueError(f"unknown retrieval mode {mode!r}")

    if mode == "rerank":
        if not reranker:
            raise ValueError("rerank mode needs a reranker model id")
        model = _cross_encoder(reranker, rerank_max_length)
        candidates = ordered[: max(1, rerank_top)]
        pairs = [(query, chunks_by_id[hit["chunk_id"]]["text"]) for hit in candidates]
        scores = model.predict(pairs)
        for hit, score in zip(candidates, scores):
            hit["fusion_score"] = hit["score"]
            hit["score"] = float(score)
        candidates.sort(key=lambda hit: -hit["score"])
        ordered = candidates

    out: List[Dict[str, Any]] = []
    for rank, hit in enumerate(ordered, start=1):
        chunk = chunks_by_id[hit["chunk_id"]]
        out.append(
            {
                "chunk_id": hit["chunk_id"],
                "doc_id": chunk["doc_id"],
                "rank": rank,
                "score": float(hit["score"]),
                "branches": hit.get("branches", {}),
                "text": chunk["text"],
                "parent_id": chunk.get("parent_id", ""),
            }
        )
    return out

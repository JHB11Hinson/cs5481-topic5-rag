"""Is the late-chunking retrieval collapse the mechanism, or the query pooling?

The late-chunking cells pool each chunk's vector as the **mean** of the token states
covering its span, while their queries go through bge-m3's ordinary **CLS**-pooled
sentence encoder (`ADR-0018`). Those are two different embedding spaces, and the dense
cells lost 0.575 of hit@10 to it. Before the report blames the mechanism, this probe
asks whether the loss survives when the query is pooled the way the spans are.

It reuses the vectors the runs already cached — no re-embedding of documents — and
embeds each query twice: once CLS-pooled, once mean-pooled over its token states.
Both are then ranked against the same document vectors, so the only thing that changes
is the query.

    HF_HUB_OFFLINE=1 python scripts/late_pooling_probe.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from ragqa import chunk as chunk_mod  # noqa: E402
from ragqa import config as config_mod  # noqa: E402
from ragqa import corpus  # noqa: E402
from ragqa.embed import EmbeddingCache, LateChunkingEmbedder  # noqa: E402
from ragqa.textutil import normalize  # noqa: E402


def _key(model: str, version: str, salt: str, text: str) -> str:
    return EmbeddingCache.key(model, version, salt, text)


def load_document_vectors(cfg, late: LateChunkingEmbedder, limit_docs: int = 0):
    """Every child chunk's cached late-chunked vector, keyed by chunk id."""
    docs = corpus.load_documents(cfg["corpus.source"])
    chunks = chunk_mod.build(
        docs,
        cfg["chunk.strategy"],
        int(cfg["chunk.size"]),
        int(cfg["chunk.overlap"]),
        int(cfg["chunk.parent_size"]),
    )
    children = [c for c in chunks if c["kind"] == "child"]
    docs_by_id = {doc["doc_id"]: doc for doc in docs}
    by_doc = {}
    for child in children:
        by_doc.setdefault(child["doc_id"], []).append(child)

    geometry = f"w{late.window_tokens}-o{late.window_overlap}-s{late.max_seq_length}"
    vectors = {}
    cache = EmbeddingCache(cfg["embed.cache_path"])
    missing = 0
    for doc_id, doc_children in by_doc.items():
        if limit_docs and len(vectors) >= limit_docs:
            break
        doc_children.sort(key=lambda c: c["char_start"])
        doc_key = hashlib.sha256(docs_by_id[doc_id]["text"].encode("utf-8")).hexdigest()
        for child in doc_children:
            key = _key(
                late.model_id,
                late.model_version,
                f"{doc_key}:{child['char_start']}:{child['char_end']}:{geometry}",
                docs_by_id[doc_id]["text"],
            )
            vector = cache.get(key)
            if vector is None:
                missing += 1
                continue
            vectors[child["chunk_id"]] = vector
    cache.close()
    return children, vectors, missing


def embed_query(late: LateChunkingEmbedder, text: str):
    """CLS pooling and mean pooling of one query, from the same forward pass."""
    import torch

    encoded = late.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    inputs = {key: value.to(late.device) for key, value in encoded.items()}
    with torch.inference_mode():
        states = late.model(**inputs).last_hidden_state[0]
    cls = states[0].float().cpu().numpy().astype(np.float64)
    mean = states[1:-1].mean(dim=0).float().cpu().numpy().astype(np.float64) if states.shape[0] > 2 else cls
    out = []
    for vector in (cls, mean):
        norm = float(np.linalg.norm(vector))
        out.append(vector / norm if norm > 0 else vector)
    return out


def rank_hits(matrix: np.ndarray, ids, query, k=10):
    scores = matrix @ query
    order = np.argsort(-scores)[:k]
    return [ids[i] for i in order]


def first_hit_rank(chunks_by_id, ranked_ids, quotes):
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        text = normalize(chunks_by_id[chunk_id]["text"])
        for quote in quotes:
            if quote and normalize(quote) in text:
                return rank
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CLS vs mean query pooling under late chunking.")
    parser.add_argument("--config", default="configs/grid/cell-recursive_parent_child-dense-late_chunking.yaml")
    parser.add_argument("--golden", default="golden/v1.jsonl")
    parser.add_argument("--out", default="notes/late-pooling-probe.md")
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args(argv)

    cfg = config_mod.load(args.config)
    late = LateChunkingEmbedder(
        model_id=cfg["embed.model_id"],
        device=cfg["embed.device"],
        max_seq_length=int(cfg["embed.late_max_seq_length"]),
        window_tokens=int(cfg["context.window_tokens"]),
        window_overlap=int(cfg["context.window_overlap"]),
        cache_path=cfg["embed.cache_path"],
    )
    children, vectors, missing = load_document_vectors(cfg, late)
    if missing:
        print(f"warning: {missing} chunk vector(s) not cached; they are skipped", file=sys.stderr)
    ids = [chunk["chunk_id"] for chunk in children if chunk["chunk_id"] in vectors]
    matrix = np.asarray([vectors[chunk_id] for chunk_id in ids], dtype=np.float64)
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in children}
    print(f"chunks with cached late vectors: {len(ids)}")

    items = []
    for line in open(args.golden, encoding="utf-8"):
        line = line.strip()
        if line:
            row = json.loads(line)
            if row.get("answerable", True) and row.get("evidence"):
                items.append(row)

    rows = []
    for item in items:
        quotes = [evidence.get("quote", "") for evidence in item["evidence"]]
        cls_query, mean_query = embed_query(late, item["question"])
        cls_hits = rank_hits(matrix, ids, cls_query, args.k)
        mean_hits = rank_hits(matrix, ids, mean_query, args.k)
        rows.append(
            {
                "item_id": item["id"],
                "type": item.get("type", ""),
                "cls_rank": first_hit_rank(chunks_by_id, cls_hits, quotes),
                "mean_rank": first_hit_rank(chunks_by_id, mean_hits, quotes),
            }
        )

    def hit_rate(field):
        return sum(1 for row in rows if row[field]) / float(len(rows))

    later = [row for row in rows if row["mean_rank"] and not row["cls_rank"]]
    earlier = [row for row in rows if row["cls_rank"] and not row["mean_rank"]]
    summary = {
        "config": args.config,
        "items": len(rows),
        "k": args.k,
        "cls_hit_at_k": round(hit_rate("cls_rank"), 4),
        "mean_hit_at_k": round(hit_rate("mean_rank"), 4),
        "cls_mrr": round(sum(1.0 / r["cls_rank"] for r in rows if r["cls_rank"]) / len(rows), 4),
        "mean_mrr": round(sum(1.0 / r["mean_rank"] for r in rows if r["mean_rank"]) / len(rows), 4),
        "mean_only": len(later),
        "cls_only": len(earlier),
        "missing_vectors": missing,
        "chunks": len(ids),
    }
    print(json.dumps(summary, indent=2))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    lines = [
        "# Query pooling under late chunking: CLS vs mean",
        "",
        f"Probe over {summary['items']} answerable golden items, k = {summary['k']}, using the "
        f"**cached** late-chunked document vectors from `{args.config}` ({summary['chunks']} chunks). "
        "Only the query pooling changes between the two columns.",
        "",
        "| query pooling | hit@k | MRR |",
        "|---|---|---|",
        f"| CLS (what the runs did, `ADR-0018`) | {summary['cls_hit_at_k']:.4f} | {summary['cls_mrr']:.4f} |",
        f"| mean over query token states (what the spans do) | {summary['mean_hit_at_k']:.4f} | {summary['mean_mrr']:.4f} |",
        "",
        f"Items the mean-pooled query recovers and the CLS one misses: **{summary['mean_only']}**; "
        f"the reverse: **{summary['cls_only']}**.",
        "",
        "## Why this matters for the report",
        "",
        "The dense cells under late chunking score 0.2750 hit@10 against 0.8500 for plain chunks. "
        "If the mean-pooled query recovers most of that gap, the loss is a property of this "
        "implementation's pooling choice, not of late chunking as a technique: the document side "
        "pools spans, so the query side must pool the same way or the two live in different spaces. "
        "If it does not recover, the loss belongs to the mechanism on this corpus and the report "
        "should say so plainly.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "HF_HUB_OFFLINE=1 python scripts/late_pooling_probe.py",
        "```",
        "",
        "## Per-item ranks",
        "",
        "| item | type | CLS rank | mean rank |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['item_id']} | {row['type']} | {row['cls_rank'] or 'miss'} | {row['mean_rank'] or 'miss'} |"
        )
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    late.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

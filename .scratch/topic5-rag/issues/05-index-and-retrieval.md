# 05: Qdrant index and three retrieval modes

**What to build:** chunks and their vectors land in a Qdrant collection keyed to one snapshot, and retrieval works in three modes — dense, hybrid with a BM25 branch fused by RRF, and hybrid plus a cross-encoder rerank. For any question a reader can see not just the fused list but which branch found the evidence and at what rank.

**Blocked by:** 04.

**Status:** done

Shipped: `ragqa/sparse.py` (BM25 + RRF), `ragqa/index.py` (`QdrantIndex`), three modes in `ragqa/retrieve.py`. Docker is unavailable, so Qdrant runs in embedded local mode at `data/index` — same client API, real on-disk footprint (22.8 MB for 2,203 chunks of 1,024 dimensions), no server process.

Measured on the 20-item golden v0 set, k = 10, same chunks and embeddings throughout:

| mode | hit@10 | MRR | nDCG@10 | wall clock |
|---|---|---|---|---|
| hybrid | 1.000 | 0.759 | 0.813 | 40 s |
| rerank, depth 8 | 0.900 | 0.850 | 0.863 | — |
| rerank, depth 12, cross-encoder truncated at 8192 | 1.000 | 0.900 | 0.926 | >10 min |
| rerank, depth 12, cross-encoder at 512 | 1.000 | 0.950 | 0.963 | 62 s |

Two lessons are in that table. The depth-8 row is a measurement artifact, not a retrieval result: the rerank stage returned eight candidates while the metric asked for ten (`ADR-0011`). And capping the cross-encoder at 512 tokens made the reranked run an order of magnitude faster *and* better on every metric — the reranker was trained for short query-document pairs, and feeding it 8,192-token inputs bought nothing but latency.

- [x] `ragqa index` builds a collection named from snapshot and embed set, idempotently
- [x] `retrieval.mode` accepts dense, hybrid, rerank; hybrid fuses with RRF at a configurable constant; rerank keeps original ranks alongside new ones
- [x] Per-branch ranks are retained in the output so the report can show which branch surfaced the evidence
- [x] Index build minutes, collection size on disk, and p50/p95 retrieval latency are recorded
- [x] Unit tests: hand-computed RRF order, a rerank that provably reorders at least one pair, and k larger than the corpus
- [x] Recall@k improves or does not, and the number is written down either way

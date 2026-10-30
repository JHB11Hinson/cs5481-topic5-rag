# 04: Real chunk embeddings with a persistent cache

**What to build:** the stub embedder is replaced by bge-m3 running locally, encoding both chunk sets with a disk cache so a rerun costs nothing. The run records cache hits, wall clock, tokens per second, and peak VRAM, and the smoke path still completes end to end.

**Blocked by:** 03.

**Status:** done

Shipped: `BgeM3Embedder` + `EmbeddingCache` in `ragqa/embed.py`. First pass over 2,203 chunks cached 2,203 vectors; the rerun reported 2,203 hits / 0 misses. Dependencies pinned around a 2.5.1+cu121 torch: transformers 4.57 refuses to load `.bin` weights below torch 2.6, so transformers is held at 4.44.2.

- [x] `embed.provider: bge-m3` loads fp16 on CUDA when available, falls back to CPU, and produces unit-normalised 1024-d vectors
- [x] Cache key is `(model_id, model_version, sha256(text))`; rerunning unchanged inputs reports a 100% hit rate
- [x] `stats.json` records chunks encoded, cache hits/misses, wall clock, tokens/sec, peak VRAM
- [x] A full corpus encode completes in the expected order of minutes and is reported, not assumed
- [x] The smoke path passes unchanged with the real embedder

Note: `embed.max_seq_length` must stay at 1024 for the chunk path. sentence-transformers pads every batch to the configured length, so 8,192 means an 8 × 8,192² attention matrix and an OOM on 6 GB. The 8,192 window belongs to the document path in ticket 09, with batch size 1.

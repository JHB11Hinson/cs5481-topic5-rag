# 09: Late chunking path on bge-m3's long window

**What to build:** documents are encoded whole — up to the model's 8,192-token window — and each chunk's vector is pooled from the token embeddings covering its span, so a chunk carries its document's context without a generated prefix. Runs beside the other two contextualization levels so all three are comparable.

**Blocked by:** 04.

**Status:** in progress — encoder written and probed, full corpus needs windowing

Shipped: `LateChunkingEmbedder` in `ragqa/embed.py` (transformers forward pass over the whole document, mean-pooled over each chunk's token span, offsets from `offset_mapping`, separate cache namespace keyed by document hash plus span), wired into `run.py` behind `context.mode: late_chunking`, plus `scripts/late_probe.py`.

Probe result on five documents: 26 chunks in 47 s with **peak VRAM 5.56 GB of 6.00** — uncomfortably close to the ceiling — and a single 53 k-char document consumed 43 s of that, because it truncated at 8,192 tokens. The fix is to window documents at roughly 2,048 tokens with overlap and pool per window; that keeps several times the context of a 512-token chunk while leaving headroom on the card.

- [x] `context.mode: late_chunking` encodes per document and mean-pools per chunk span, unit-normalising the result
- [x] Cache lives in its own namespace keyed by document text and chunk span, separate from the chunk-level cache
- [ ] Documents over the window are windowed with overlap and the window count is reported
- [x] A test shows the pooled vector differs from the standalone chunk vector for a chunk that is ambiguous alone but unambiguous in context
- [x] Peak VRAM is recorded for the document path, where an OOM would actually appear
- [ ] A/B against plain and prefix levels is reported on the same items

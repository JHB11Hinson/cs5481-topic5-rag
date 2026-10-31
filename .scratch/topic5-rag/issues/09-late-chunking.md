# 09: Late chunking path on bge-m3's long window

**What to build:** documents are encoded whole — up to the model's 8,192-token window — and each chunk's vector is pooled from the token embeddings covering its span, so a chunk carries its document's context without a generated prefix. Runs beside the other two contextualization levels so all three are comparable.

**Blocked by:** 04.

**Status:** done — implemented, windowed, and measured; the mechanism fails here

Shipped: `LateChunkingEmbedder` in `ragqa/embed.py` (transformers forward pass over the whole document, mean-pooled over each chunk's token span, offsets from `offset_mapping`, separate cache namespace keyed by document hash plus span), wired into `run.py` behind `context.mode: late_chunking`, plus `scripts/late_probe.py`.

Probe result on five documents: 26 chunks in 47 s with **peak VRAM 5.56 GB of 6.00** — uncomfortably close to the ceiling — and a single 53 k-char document consumed 43 s of that, because it truncated at 8,192 tokens. The fix is to window documents at roughly 2,048 tokens with overlap and pool per window; that keeps several times the context of a 512-token chunk while leaving headroom on the card.

- [x] `context.mode: late_chunking` encodes per document and mean-pools per chunk span, unit-normalising the result
- [x] Cache lives in its own namespace keyed by document text and chunk span, separate from the chunk-level cache
- [x] Documents over the window are windowed with overlap and the window count is reported
- [x] A test shows the pooled vector differs from the standalone chunk vector for a chunk that is ambiguous alone but unambiguous in context
- [x] Peak VRAM is recorded for the document path, where an OOM would actually appear
- [x] A/B against plain and prefix levels is reported on the same items

## Resolution

Documents are encoded in windows of 2,048 tokens with 256 of overlap, the window count
and peak VRAM are recorded per run (`context_stats.json`), and the cached span vectors
are keyed by the window geometry so a different window cannot silently reuse them
(`ADR-0015`). Queries go through the ordinary sentence encoder — the document encoder
refuses them with a sentence rather than an `AttributeError` (`ADR-0018`), which is what
six cells died of before the fix.

The A/B against plain, on the same items: late chunking versus plain on retrieval is
**b = 0, c = 54 of 240 paired items, p < 0.000001**. Dense cells fall to hit@10 0.2750
from 0.8500; hybrid and rerank are rescued to 0.8750 by the lexical branch and the
reranker, with MRR still down.

A probe settles why (`scripts/late_pooling_probe.py`, `notes/late-pooling-probe.md`):
mean-pooling the query the way the spans are pooled makes it **worse**, hit@10 0.2750 →
0.0250, 0 recovered and 10 lost. Mean-pooled token states are off-distribution for a
CLS-trained encoder, and the damage is on the document side. So document-level context
remains untested here; testing it needs a mean-pooling encoder, which is the first thing
we would run with more time.

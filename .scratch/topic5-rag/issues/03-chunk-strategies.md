# 03: Two chunk strategies over the real snapshot

**What to build:** the pipeline runs twice over the real corpus with two named chunk strategies — a fixed word-window with overlap, and a recursive parent-child splitter that respects headings before paragraphs before sentences. Both produce chunk sets whose ids are stable across processes, plus a stats file that makes the difference legible before any retrieval happens.

**Blocked by:** 02.

**Status:** done

Shipped: `ragqa/chunk.py` rebuild per `ADR-0010`, plus `python -m ragqa.chunk`. Measured: fixed 2,318 children (mean 327.7 words, 57.5% end mid-sentence, 53.0% contain a table row); recursive 2,203 children + 1,536 parents (mean 311.9, 18.7% mid-sentence, 51.4% table rows). Atomic units above 1,024 words split on line boundaries — a 2,088-word table otherwise caused a GPU out-of-memory error downstream.

- [x] `ragqa chunk` writes `chunks.jsonl` and `chunk_stats.json` for each strategy
- [x] Chunk ids are deterministic across processes and machines; the derivation is documented
- [x] Every child chunk in the recursive set has a parent covering its character range, and every parent is exactly the union of its children's ranges
- [x] `chunk_stats.json` reports count, mean/p95 tokens, share ending mid-sentence, table-splitting rate, and over-length count
- [x] Unit tests cover a document shorter than one chunk, one paragraph longer than the maximum, a table crossing a boundary, and a heading change mid-chunk
- [x] Golden evidence quotes still locate correctly through char offsets after re-chunking

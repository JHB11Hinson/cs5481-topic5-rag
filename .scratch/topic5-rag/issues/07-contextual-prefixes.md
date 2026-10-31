# 07: Contextual prefixes as a configurable level

**What to build:** each chunk can acquire a short generated sentence situating it inside its document, prepended before indexing into both the dense and the sparse representation. The pipeline runs both ways on the same golden items so the difference is a number, not an opinion.

**Blocked by:** 06.

**Status:** done — the mechanism works; the A/B is a null result

- [x] `context.contextual_prefix: true` produces `chunks_contextual.jsonl` with prefix, contextual text, and the original text preserved
- [x] Prefixes are cached by `(model, prompt_hash)`; a rerun reports 100% hits
- [x] Sparse index terms include prefix tokens, asserted by a test rather than assumed
- [x] Cost in ¥, token counts, and p50 prefix length are recorded
- [x] A 20-item human audit lands in `notes/prefix-audit.md`; above a 20% fail rate the ticket is not done
- [x] The A/B on the golden set is reported with both retrieval and citation metrics

## Resolution

2,203 prefixes were generated for ¥0.48 (the first figure under-counted output tokens)
and a rerun reports 2,203/2,203 cache hits, 0 tokens, ¥0. The 20-item audit fails
nothing (`notes/prefix-audit.md`), and the sparse index is asserted to carry prefix
tokens by a test rather than assumed.

The A/B is the interesting part and it is **null**: six usable pairs, hit@10 −0.025 in
all three `fixed` pairs and +0.025 in `recursive/dense`, every paired bootstrap interval
containing zero, and the sign splitting by chunk strategy rather than by retrieval mode
— an interaction with one cell per corner. Citation precision moves between −0.018 and
+0.042, none significant. `notes/prefix-ab.md`.

The prefix enters the index only; the generation prompt keeps the raw chunk, so any
citation effect comes through retrieval (`ADR-0013`). What it costs is ¥0.48 and 35
minutes of generation for an index that is 12 bytes larger and measurably no better.

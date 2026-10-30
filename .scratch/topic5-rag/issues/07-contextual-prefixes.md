# 07: Contextual prefixes as a configurable level

**What to build:** each chunk can acquire a short generated sentence situating it inside its document, prepended before indexing into both the dense and the sparse representation. The pipeline runs both ways on the same golden items so the difference is a number, not an opinion.

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] `context.contextual_prefix: true` produces `chunks_contextual.jsonl` with prefix, contextual text, and the original text preserved
- [ ] Prefixes are cached by `(model, prompt_hash)`; a rerun reports 100% hits
- [ ] Sparse index terms include prefix tokens, asserted by a test rather than assumed
- [ ] Cost in ¥, token counts, and p50 prefix length are recorded
- [ ] A 20-item human audit lands in `notes/prefix-audit.md`; above a 20% fail rate the ticket is not done
- [ ] The A/B on the golden set is reported with both retrieval and citation metrics

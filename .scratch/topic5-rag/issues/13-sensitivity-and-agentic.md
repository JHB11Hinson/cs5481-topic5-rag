# 13: Sensitivity sweeps and the bounded agentic loop

**What to build:** three dose-response curves — retrieval depth, chunk size, and retrieval hops — where the hop curve requires an actual bounded loop: when the first round fails to surface evidence, the question is decomposed and retrieved again, with a hard round cap and a recorded stop reason.

**Blocked by:** 12.

**Status:** ready-for-agent

- [ ] `retrieval.k` sweep at 5, 10, 20, 40 produces a curve over the 40 answerable items
- [ ] Chunk-size sweep at 256, 512, 1024 produces its curve
- [ ] The agentic loop decomposes the question after a failed round, retrieves again, honours a hard cap, and records one of: hit on first round, hit after rewrite, cap reached, abstained
- [ ] Hop curve at 1, 2, 3 reports ΔRecall, Δcitation precision, Δlatency, and Δ¥ per thousand questions
- [ ] Determinism: temperature 0 plus a response cache means a rerun of any hop count reproduces its metrics
- [ ] The report can state, with numbers, at which hop the loop stops paying for itself

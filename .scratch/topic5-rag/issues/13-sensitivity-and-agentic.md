# 13: Sensitivity sweeps and the bounded agentic loop

**What to build:** three dose-response curves — retrieval depth, chunk size, and retrieval hops — where the hop curve requires an actual bounded loop: when the first round fails to surface evidence, the question is decomposed and retrieved again, with a hard round cap and a recorded stop reason.

**Blocked by:** 12.

**Status:** done — three curves, and the hop loop stops paying at hop one

- [x] `retrieval.k` sweep at 5, 10, 20, 40 produces a curve over the 40 answerable items
- [x] Chunk-size sweep at 256, 512, 1024 produces its curve
- [x] The agentic loop decomposes the question after a failed round, retrieves again, honours a hard cap, and records one of: hit on first round, hit after rewrite, cap reached, abstained
- [x] Hop curve at 1, 2, 3 reports ΔRecall, Δcitation precision, Δlatency, and Δ¥ per thousand questions
- [x] Determinism: temperature 0 plus a response cache means a rerun of any hop count reproduces its metrics
- [x] The report can state, with numbers, at which hop the loop stops paying for itself

## Resolution

Ten cells in `configs/sweeps/`, each differing from the reference cell in one parameter
and nothing else (asserted by a full key diff), depth at least k everywhere (`ADR-0011`),
and the forty answerable items selected by stratum rather than by file position — the old
`golden.limit: 40` slice gave every point zero negatives and printed its abstention
columns as `0.0` instead of `0/0`.

The agentic loop decomposes after a failed round, honours its cap, and records exactly one
of `hit_first_round` / `hit_after_rewrite` / `cap_reached` / `abstained` per item in
`hop_stats.json`. Its trigger is the v1 rerank working point (0.426134), re-derived after
the calibration moved, and a test pins that equality rather than the old divergence.

The curves and the break-even sentence are in `reports/sweeps/` and `notes/sweeps.md`.

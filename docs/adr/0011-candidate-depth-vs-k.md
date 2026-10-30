# Candidate depth must be at least k, or recall@k measures truncation

Any configuration measured with recall@k keeps at least k candidates after the last stage. Rerank therefore rescored `max(k, rerank_top)` candidates rather than the fixed 8 it started with.

The first reranked run scored worse than plain hybrid on hit@10 (0.90 versus 1.00) while scoring better on MRR and nDCG (0.850 versus 0.759; 0.863 versus 0.813). Nothing about the reranker was worse: the rerank stage returned only eight candidates, and a ten-item recall was then computed over an eight-item list. Two items of headroom had been deleted by a parameter that had nothing to do with retrieval quality. Re-running with twelve candidates restored hit@10 to 1.00 and pushed MRR to 0.900 and nDCG@10 to 0.926 — all three better than hybrid, which is the result the first run appeared to contradict.

This is the failure mode a matrix invites: with eighteen cells and three factors, a parameter that interacts with the *metric* rather than with the system produces a number that looks like evidence and is not. The rule costs nothing to obey.

## Consequences

Configurations now record both `k` and the effective candidate depth, and the run fails loudly if the depth falls below `k`. The chunk-size and hop sweeps inherit the same rule. When the report compares recall@k across modes, the depth column is printed next to the metric so a reader can see the confound was controlled rather than assume it.

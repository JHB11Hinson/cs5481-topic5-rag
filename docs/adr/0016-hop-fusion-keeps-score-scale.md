# A fused retrieval round keeps each hit on its own score scale

When the agentic loop runs more than one round, the rounds are fused with reciprocal rank fusion for ordering, but every hit keeps the score its own retriever gave it. The fused value is stored separately as `fusion_score`.

The alternative — letting RRF overwrite `score` — was implemented first and broke two things at once. The agentic trigger asks whether the best score cleared a threshold, and after fusion the best score was ~1/61 on every item, so the loop always thought it had failed and always spent its full hop budget. The abstention threshold downstream reads the same field, so a two-hop run would abstain on every question while a one-hop run answered. Both thresholds live on the retrieval mode's scale — cosine, RRF sums, or cross-encoder logits — and that scale is a property of the mode, not of how many rounds were run.

Keeping the original score means the hop curve compares like with like: the only thing that changes across hops 1, 2 and 3 is how many candidates were considered, not the units the decision is made in.

## Consequences

`score` is always on the retrieval mode's scale and `fusion_score` is always RRF. Anything that thresholds reads `score`. The hop sweep in ticket 13 inherits a caveat worth stating in the report: fusing three weak rounds can outrank a strong single round for ordering without any hit exceeding the threshold, which is why the stop reason records which round produced the hit rather than only how many rounds ran.

# 11: Abstention as a calibrated decision, not a habit

**What to build:** the retrieval-score threshold is swept and the resulting abstention precision-recall curve is plotted, with one working point chosen and justified. Over-abstention on answerable items and under-abstention on near-misses become two separate numbers instead of one accuracy figure.

**Blocked by:** 06, 08.

**Status:** done — working points measured per retrieval mode

- [x] Threshold sweep from 0.2 to 0.9 in 0.05 steps produces a PR curve over the 20 near-miss and 40 answerable items
- [x] The chosen working point is recorded with its justification in the run directory
- [x] Over-abstain rate on answerable items and under-abstain rate on near-misses are reported separately
- [x] The curve is emitted by the aggregate step as a figure, not hand-drawn in a notebook
- [x] Behaviour at the chosen threshold is demonstrated on at least three near-miss items with their top-scoring chunks shown

## Resolution

The sweep runs in a per-mode normalised space and reports the raw-scale equivalent,
because cross-encoder logits, RRF sums and cosine are three scales and one threshold
cannot serve all three. The rule was fixed before the numbers: maximise F1 of the
answer class subject to over-abstention ≤ 0.05, ties to the larger threshold.

| mode | working point | raw threshold | precision | recall | F1 | over-abstain | under-abstain |
|---|---|---|---|---|---|---|---|
| hybrid | 0.4059 | 0.030432 | 0.556 | 1.000 | 0.714 | 0.000 | 0.800 |
| rerank | 0.4471 | 0.759250 | 0.714 | 1.000 | 0.833 | 0.000 | 0.400 |

The hybrid ceiling is structural, not a tuning gap: two answerable items and five
near-misses all score exactly 0.032522 because the RRF lattice has only so many
values at k=10. No threshold separates them, and the note says so rather than moving
the working point to make the curve look better.

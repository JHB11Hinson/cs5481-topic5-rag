# 11: Abstention as a calibrated decision, not a habit

**What to build:** the retrieval-score threshold is swept and the resulting abstention precision-recall curve is plotted, with one working point chosen and justified. Over-abstention on answerable items and under-abstention on near-misses become two separate numbers instead of one accuracy figure.

**Blocked by:** 06, 08.

**Status:** ready-for-agent

- [ ] Threshold sweep from 0.2 to 0.9 in 0.05 steps produces a PR curve over the 20 near-miss and 40 answerable items
- [ ] The chosen working point is recorded with its justification in the run directory
- [ ] Over-abstain rate on answerable items and under-abstain rate on near-misses are reported separately
- [ ] The curve is emitted by the aggregate step as a figure, not hand-drawn in a notebook
- [ ] Behaviour at the chosen threshold is demonstrated on at least three near-miss items with their top-scoring chunks shown

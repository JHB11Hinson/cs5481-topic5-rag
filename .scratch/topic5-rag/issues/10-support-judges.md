# 10: Two support judges and their agreement

**What to build:** claims that survive containment are judged for support twice — a local NLI cross-encoder and a hosted model — and the two are calibrated against 30 hand-labelled claims, so the report can state how much either judge can be trusted.

**Blocked by:** 06, 08.

**Status:** done — hosted judge gates reporting, NLI is a diagnostic

- [x] `ragqa verify` adds NLI verdicts and judge verdicts per claim, with the judge's one-line reason stored
- [x] Citation precision, citation recall, and span hit rate are computed from verdicts, not from the generator's self-report
- [x] A confusion table between NLI and judge verdicts is emitted
- [x] `notes/judge-calibration.md` holds 30 hand-labelled claims, Cohen's kappa for each judge against the human, and a stated decision on which layer gates reporting
- [x] Judge cost and call counts are recorded per configuration

## Resolution

30 claims were labelled by hand and both judges scored against them:
Cohen's kappa **0.857** for `deepseek-v4-pro` (agreement 0.933, precision 1.000,
recall 0.900) and **0.595** for the local NLI cross-encoder (agreement 0.833).
The 0.60 bar was fixed before the numbers were seen, so NLI does not gate anything;
`notes/judge-calibration.md` states the decision and shows every disagreement.

All five NLI↔judge disagreements are `nli_only` — NLI never rejects what the judge
accepts — so its errors inflate precision rather than cost recall, and its four false
positives are exactly relation reversals and in-chunk distractors.

The layer had been **inverted end to end**: the checkpoint's label order is
`[entailment, neutral, contradiction]`, not MNLI's. The first calibration run scored
kappa −0.33 and recall 0.05. It now reads `id2label`, and a test pins the order.

Set composition is stated in the note rather than smoothed: the real-generation runs
hold 50 claims, 47 survive containment, **none is false** — real generator error shows
up as a containment failure, which never reaches a judge. The 30-item set is therefore
20 verbatim claims plus 10 controlled negatives with one documented edit each.

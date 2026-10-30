# Abstention as a calibrated decision

Ticket 11. The retrieval score is swept, the resulting precision-recall curve is
plotted, and one working point per retrieval mode is chosen by a rule that was
fixed before the numbers were seen. The command is at the bottom.

Everything below is arithmetic over the eight finished run directories in
`runs/`. No model was called to produce it: `reports/abstention/` is rebuilt from
`predictions.jsonl` alone.

## What was swept

Per golden item, the swept quantity is the *top* retrieval score — the maximum
over `retrieved[]`, which is the number `generate.abstain_score_threshold` is
compared against. The label is the golden `answerable` flag: an answerable item is
a **positive** that should be answered, a near-miss item is a **negative** that
should be abstained on. Decision rule: answer iff normalized score >= t, matching
`generate.py`, which abstains when `score < threshold`.

| mode | runs | scale of the raw score | observed top-score range |
|---|---|---|---|
| hybrid | `real-hybrid-*` (2) | RRF fused sum, ~1/(rrf_k + rank) | 0.0164 – 0.0328 |
| rerank | `real-rerank-*` (3) | cross-encoder score in [0, 1] | 0.1012 – 0.9988 |
| llm | `real-llm-*` (3) | same cross-encoder score (rerank retrieval) | 0.1012 – 0.9988 |

Ten answerable and ten near-miss items per mode, after deduplication: each mode's
runs contain the identical golden set, so one row per `item_id` survives and the
newest run's observation wins. Pooling repeats would have doubled every count
without adding a single independent item.

### The scale problem, in one number

The three modes cannot share a threshold, and the run directories show the damage
that a shared number does:

| run | `generate.abstain_score_threshold` | what happened |
|---|---|---|
| `real-hybrid-...091924` | 0.2 | 20 of 20 items abstained — the RRF scale never reaches 0.2 |
| `real-hybrid-...092148` | 0.01 | 20 of 20 answered — 0.01 is below every top score |
| `real-rerank-...095541` | 0.0 | threshold inert; abstention came from the stub's grounding check |
| `real-llm-...113604` | -100.0 | threshold disabled; the model abstained on 9 of 10 near-misses by itself |

Same config key, four different meanings. Hence the sweep runs in a **normalized
space** and reports the **raw equivalent** of every threshold, because the raw
number is the only thing that can be written back into a config.

Transform per mode, fitted on that mode's own top-score distribution:

- `dense` — **identity**. Cosine similarity is already a bounded similarity.
- `hybrid`, `rerank`, `llm` — **z-score then standard normal CDF**:
  `p = Phi((score - mean) / stdev)`, inverted as
  `raw = mean + stdev * Phi^-1(p)`. Fitted values are recorded in
  `working-points.json` (`hybrid`: mean 0.031268, stdev 0.003510, n = 20;
  `rerank`/`llm`: mean 0.793426, stdev 0.256976, n = 20).

The map is strictly monotone, so it cannot reorder items, and it is invertible, so
`raw_threshold` is exact rather than approximate. `t = 0.5` is the mode's own mean
score — the one point on the curve whose meaning survives a change of scale.

Grid: 18 points across [0.2, 0.9]. The ticket fixes both the interval and the
point count, which are inconsistent at a 0.05 step (that interval holds 15
points); the step is flattened to 0.0412 so that neither endpoint moves. Points
whose raw equivalent exceeds the highest score the mode ever produced are kept in
the CSV but hidden from the figure: they are extrapolations of the fitted normal,
not thresholds any query can cross. Three of eighteen are extrapolated in
`rerank`/`llm`, six of eighteen in `hybrid`.

## The shape of the curve

**hybrid** (`reports/abstention/hybrid-pr.png`) is not a curve, it is a plateau
followed by a cliff. From t = 0.2 to t = 0.6118 precision stays between 0.50 and
0.58 while recall sits at 1.00 and then 0.70: the threshold moves, the separation
does not. The reason is visible in the raw values — **two answerable items and five
near-misses all score exactly 0.032522**, while five answerable items score
0.032787, a gap of 0.000265 on a scale whose whole range is 0.0164–0.0328. Any
threshold in that gap must decide all seven tied items the same way. At
t = 0.6529 precision reaches 1.00 only by dropping half the answerable items
(recall 0.50, over-abstain 0.50), and by t = 0.6941 no item is answered at all.

That plateau is a property of the quantity being thresholded, not of the tuning.
An RRF sum is built from reciprocal ranks, so it takes a handful of lattice values
(0.032787 = 1/61 + 1/61, 0.032522 = 1/61 + 1/62, 0.016393 = 1/61) and it is
*symmetric* in the two classes: an unanswerable question that both branches place
first is indistinguishable from a real one by this score. **Precision collapses
here structurally, not at the end of the sweep.**

**rerank** and **llm** are the staircase one expects from a well-behaved score: at
t = 0.2 precision 0.625 with recall 1.00 and under-abstention 0.60; by t = 0.3235
precision 0.714 with under-abstention 0.40; the unconstrained F1 peak is at
t = 0.6529 (precision 0.818, recall 0.90, F1 0.857) and it costs one answerable
item; at t = 0.7765 precision reaches 1.00 with recall 0.50. Precision collapses
to 0 only past raw 0.9988, where the threshold exceeds every score in the corpus
and nothing is answered — an uninteresting collapse, which is why those points are
hidden in the figure.

The rerank and llm curves are **identical**, because retrieval is identical;
`llm` differs only in that a model writes the answer. That makes the two rows one
piece of evidence about the score and two different pieces of evidence about
abstention end to end — not two independent confirmations.

## Why the two error types are reported separately

`evaluate.py` already refuses to fold them into one number, and this sweep keeps
that split for a sharper reason: they are not two ways of being wrong, they are
two different failures with opposite fixes.

- **Over-abstention on answerable items** is the system withholding what its
  knowledge base contains. It is silent, it is what users experience as "this
  thing is useless", and it is the failure that the shipped hybrid config
  (threshold 0.2) had 100% of.
- **Under-abstention on near-misses** is the system answering what it cannot
  support. It is loud, it is the failure the report's citation verifier catches
  after the fact, and it is the one a threshold can actually move.

A single accuracy figure hides the trade because the two errors trade against each
other one-for-one: on a balanced set, "always answer" and "always abstain" both
score 0.5 while being the two worst possible policies. Reporting them separately
is what makes the working-point rule stateable at all, and it is what makes the
hybrid result legible — over-abstention 0.00 with under-abstention 0.80 is a
completely different diagnosis from the reverse, and no accuracy number
distinguishes them.

## The working point the experiments should adopt

Rule, fixed in advance: **maximise F1 of the answer class subject to
over-abstention on answerable items <= 0.05**; if the budget is infeasible at every
t, take the smallest achievable over-abstention rate; ties go to the largest t.

| mode | t (normalized) | **raw `generate.abstain_score_threshold`** | precision | recall | over-abstain | under-abstain |
|---|---|---|---|---|---|---|
| hybrid | 0.4059 | **0.030432** | 0.556 | 1.000 | 0.000 | 0.800 |
| rerank | 0.4471 | **0.759250** | 0.714 | 1.000 | 0.000 | 0.400 |
| llm | 0.4471 | **0.759250** | 0.714 | 1.000 | 0.000 | 0.400 |

All three are feasible and all three land on "the largest threshold that still
answers every answerable item" — because with ten positives the over-abstention
budget of 0.05 rounds down to *zero* abstentions on answerable items, and F1 is
monotone increasing in t inside that feasible set. The budget, not the F1
frontier, decides these points.

What each of those numbers is worth:

1. **rerank / llm: adopt 0.759250 as a floor, not as the abstention mechanism.**
   It rejects 6 of 10 near-misses before generation at no cost to any answerable
   item (over-abstention 0.000, precision 0.714). It does not finish the job: 4 of
   10 near-misses still clear it (U005 Terraform, U007 admission controller, U001
   `-namespace` default), scoring 0.89–0.97 on passages that are topically exact —
   see `near-miss-examples.md`. The model's own abstention caught 9 of 10 in
   `real-llm-*`, so the threshold is a cheap pre-filter in front of the model, and
   the pair is what to report. The unconstrained F1 peak (t = 0.6529, raw 0.8945,
   F1 0.857) is *not* adopted: it buys 0.043 F1 by abstaining on a real question.
2. **hybrid: adopt 0.030432 only if a floor is wanted, and do not expect it to
   work.** Under-abstention 0.800 at the working point: eight near-misses out of
   ten clear the best threshold that keeps every answerable item, because the
   score ties them with real questions. The correct conclusion is not a better
   hybrid threshold, it is that a rank-fusion score is not a confidence and that
   hybrid needs the reranker (or the model) to decide abstention. The old default
   of 0.2 on this mode abstained on everything and nobody noticed for a day.
3. **dense: nothing to adopt.** No dense run exists on disk, so this sweep has no
   evidence for it and the identity transform means its t values are not
   comparable with the other rows. Re-run the sweep once a dense run exists; do
   not copy 0.759250 into a dense config (cosine for answerable items can easily
   sit below that).
4. **Golden v0 is the ceiling on all of this.** Ten positives and ten near-misses
   mean every rate moves in steps of 0.1, and the 0.05 budget is arithmetically
   the same as "zero". The working points are a v0 estimate; golden v1 (40
   answerable / 20 near-miss, ADR-0005) is what turns them into resolution. The
   sweep needs no change to ingest v1 — it is the same arithmetic over more rows.

## Near-misses that score high anyway

`reports/abstention/near-miss-examples.md` shows the three hardest near-misses per
mode with their top-three chunks, so the score can be read next to the text. The
pattern is consistent: the passages are *about* the right subject and contain none
of the requested fact. U001 asks for the `-namespace` default of `vault operator
init` in Vault 1.22 and retrieves `docs/commands/operator/init` at 0.890; U005 asks
for a Terraform resource name and retrieves the AWS auth page at 0.965. A
cross-encoder scores *relevance*, and a near-miss is by construction relevant
without being sufficient — which is why the residual under-abstention has to be
spent by a reader, and why the 0.759 floor is defensible only as a pre-filter.

The examples also show the two layers disagreeing item by item: U001 and U007 both
clear the 0.759 floor (0.890 and 0.925) and the model nevertheless abstained on
both in `real-llm-*` (`run-time abstained: True`). That is the pre-filter /
reader split written down at the item level, and it is why the recommendation
above keeps both.

## Regenerate

A run family whose name does not name a retrieval mode (`ctx-plain-*`,
`ctx-prefix-*`, `ctx-late-*`) is skipped with a warning and listed in
`working-points.json` under `unrouted_runs`: those runs vary the *context* mode on
top of `retrieval.mode: rerank`, so their score scale is rerank's, but pooling them
with `real-rerank-*` would mix configurations in one curve. Sweeping them needs
either a run name that carries the mode or a `ModeSpec` entry — a one-line change
in `MODES`, no change to the arithmetic.

```bash
python -m ragqa sweep abstention --runs runs --out reports            # from this repo
python -m ragqa sweep abstention --runs "D:/DE Project/Project/runs" --out reports  # from a worktree without runs/
python -m ragqa sweep abstention --runs runs --out reports --modes rerank
python -m ragqa.selftest                                              # 70 tests
```

Writes `reports/abstention/{hybrid,rerank,llm}-pr.{csv,png}`,
`reports/abstention/working-points.json` (chosen t, raw threshold, transform fit,
justification, source runs) and `reports/abstention/near-miss-examples.md`. The
CSV columns are `t, precision, recall, over_abstain_rate_on_answerable,
under_abstain_rate_on_near_miss, raw_threshold`.

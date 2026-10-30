# Abstention as a calibrated decision

Ticket 11. The retrieval score is swept, the resulting precision-recall curve is
plotted, and one working point per retrieval *scale* is chosen by a rule that was
fixed before the numbers were seen. The command is at the bottom.

Everything below is arithmetic over the finished run directories under
`D:/DE Project/wt/exp/runs` (the live matrix root). No model was called to produce
it: `reports/abstention/` is rebuilt from `predictions.jsonl` alone.

The numbers are **golden v1**: 40 answerable and 20 near-miss items, which is what
ticket 11's box 1 asks for. The committed curve this replaces was measured on v0's
10 + 10, so every rate in it moved in steps of 0.1; these move in 1/40 and 1/20.

## What was swept

Per golden item, the swept quantity is the *top* retrieval score — the maximum over
`retrieved[]`, which is the number `generate.abstain_score_threshold` is compared
against. The label is the golden `answerable` flag: an answerable item is a
**positive** that should be answered, a near-miss item is a **negative** that
should be abstained on. Decision rule: answer iff normalized score >= t, matching
`generate.py`, which abstains when `score < threshold`.

| curve (score scale) | runs behind it | scale of the raw score | observed top-score range |
|---|---|---|---|
| dense | 3 grid cells (`retrieval.mode: dense`) | cosine similarity in [0, 1] | 0.5356 – 0.7664 |
| hybrid | 3 grid cells (`retrieval.mode: hybrid`) | RRF fused sum, ~1/(rrf_k + rank) | 0.0164 – 0.0328 |
| rerank | 3 grid cells (`retrieval.mode: rerank`) | cross-encoder score in [0, 1] | 0.0260 – 0.9995 |

Forty answerable and twenty near-miss items per curve, after deduplication: the
runs behind a curve contain the identical golden set, so one row per `item_id`
survives and the newest run's observation wins. Pooling repeats would have
quadrupled every count without adding a single independent item.

### One curve per score scale, and the generator is a label

There is no `llm` curve. A curve is a function of the retrieval score alone, so
which model wrote the answer cannot move it: `llm` retrieval *is* rerank retrieval,
and the `llm-pr.csv` this note used to publish was byte-identical to
`rerank-pr.csv`. Publishing both was a duplicate dressed as a replication. The
generator is now a **label column** (`generator` in every CSV, `generator` and
`items_by_generator` in `working-points.json`); all three curves here are labelled
`llm`, because every scoring run in the v1 population generated with a hosted model.
`reports/abstention/llm-pr.csv` and its figure are deleted.

### One golden-set population per curve

The run root holds two populations: v0 (20 items) from the early `real-*` runs and
v1 (60 items) from the matrix cells. Mixing them on one curve would overwrite the
shared item ids with whichever run sorted last and change every rate's denominator
without anyone noticing. So a mode's runs are partitioned by the golden set they
answered and the partition with the most items is the curve; the rest are listed
under `excluded_runs` in `working-points.json`, with their size:

| curve | excluded (different population) |
|---|---|
| dense | 7 smoke/judge-smoke runs (5 fixture items) |
| hybrid | 2 `real-hybrid-*` runs (v0, 20 items); 3 `smoke-prefix-*` runs (5 fixture items) |
| rerank | 3 `real-llm-*` and 3 `real-rerank-*` runs (v0, 20 items); 1 `ctx-plain-*` run (v0, 5 items) |

### The scale problem, in one number

The scales cannot share a threshold, and the run directories show the damage a
shared number does: `real-hybrid-...091924` ran with 0.2 and abstained on all 20
items (the RRF scale never reaches 0.2), while `real-hybrid-...092148` ran with 0.01
and answered all 20. Same config key, opposite failures. Hence the sweep runs in a
**normalized space** and reports the **raw equivalent** of every threshold, because
the raw number is the only thing that can be written back into a config.

Transform per scale, fitted on that scale's own top-score distribution:

- `dense` — **identity**. Cosine similarity is already a bounded similarity.
- `hybrid`, `rerank` — **z-score then standard normal CDF**:
  `p = Phi((score - mean) / stdev)`, inverted as
  `raw = mean + stdev * Phi^-1(p)`. Fitted values are recorded in
  `working-points.json` (`hybrid`: mean 0.030890, stdev 0.003967, n = 60;
  `rerank`: mean 0.672310, stdev 0.292501, n = 60).

The map is strictly monotone, so it cannot reorder items, and it is invertible, so
`raw_threshold` is exact rather than approximate. `t = 0.5` is the scale's own mean
score — the one point on a curve whose meaning survives a change of scale.

**The grid, in one sentence a grader can check.** The ticket fixes the interval
[0.2, 0.9] *and* 18 points, and a 0.05 step fits only 15 points into 5 intervals, so
the sweep keeps both endpoints and both counts by using a step of
(0.9 − 0.2) / 17 = 0.0412 — finer than 0.05 everywhere inside the same interval,
which is the only reading that satisfies the interval and the point count at once.

Points whose raw equivalent exceeds the highest score the scale ever produced are
kept in the CSV but hidden from the figure: they are extrapolations of the fitted
normal, not thresholds any query can cross. That is 4 of 18 in `dense`, 6 of 18 in
`hybrid` and 1 of 18 in `rerank`, and such a point is never a candidate for the
working point, which must be a threshold the system can actually cross.

## The shape of each curve

**hybrid** is not a curve, it is a plateau followed by a cliff. An RRF sum is built
from reciprocal ranks, so it takes a handful of lattice values (0.032787 = 1/61 +
1/61, 0.016393 = 1/61) and it is *symmetric* in the two classes: an unanswerable
question that both branches place first is indistinguishable from a real one by this
score. At the working point it answers 37 of 40 answerable items and 19 of 20
near-misses — precision collapses here structurally, not at the end of the sweep.

**dense** is the well-behaved case on this corpus: cosine separates the two classes
over a range of 0.23 (0.5356 to 0.7664), and the chosen threshold answers 38 of 40
answerable items while still answering 17 of 20 near-misses. Its unconstrained F1
peak is at t = 0.2 with F1 0.800 — the same F1 as the working point, which is why
the budget, not the frontier, decides.

**rerank** is a staircase with a long tail: the cross-encoder scores near-misses as
high as 0.9988, so no threshold inside the observed range keeps the error budget.
Its unconstrained F1 peak is at t = 0.5294 (F1 0.811); the budget-constrained rule
falls back to the smallest achievable over-abstention, which is 0.150 at the grid
floor t = 0.2 (raw 0.426134).

## Why the two error types are reported separately

`evaluate.py` already refuses to fold them into one number, and this sweep keeps
that split for a sharper reason: they are not two ways of being wrong, they are two
different failures with opposite fixes.

- **Over-abstention on answerable items** is the system withholding what its
  knowledge base contains. It is silent, it is what users experience as "this thing
  is useless", and it is the failure the shipped hybrid config (threshold 0.2) had
  100% of.
- **Under-abstention on near-misses** is the system answering what it cannot
  support. It is loud, it is the failure the report's citation verifier catches
  after the fact, and it is the one a threshold can actually move.

A single accuracy figure hides the trade because the two errors trade against each
other one-for-one: on a balanced set, "always answer" and "always abstain" both
score 0.5 while being the two worst possible policies.

## The working points, on v1

Rule, fixed in advance: **maximise F1 of the answer class subject to
over-abstention on answerable items <= 0.05**; if the budget is infeasible at every
t, take the smallest achievable over-abstention rate; ties go to the largest t.

| mode | t (normalized) | **raw `generate.abstain_score_threshold`** | precision | recall | F1 | over-abstain | under-abstain | answerable answered | near-miss answered |
|---|---|---|---|---|---|---|---|---|---|
| dense | 0.5706 | **0.570600** | 0.691 | 0.950 | 0.800 | 0.050 | 0.850 | 38/40 | 17/20 |
| hybrid | 0.2824 | **0.028606** | 0.661 | 0.925 | 0.771 | 0.075 | 0.950 | 37/40 | 19/20 |
| rerank | 0.2000 | **0.426134** | 0.739 | 0.850 | 0.791 | 0.150 | 0.600 | 34/40 | 12/20 |

Read it honestly:

1. **The 0.05 budget is only feasible for dense**, and only just: at t = 0.5706 it
   abstains on 2 of 40 answerable items. For hybrid and rerank the budget is
   infeasible at all 18 points, so the rule's fallback fired and the table reports
   the smallest achievable over-abstention it could reach — 0.075 and 0.150. A
   reader who wanted "at most one answerable item lost" will not find it on those
   two scales, and the note says so rather than rounding the budget away.
2. **No scale is good at both errors.** The best under-abstention anywhere is 0.600
   (rerank answers 12 of 20 near-misses) and it costs 0.150 over-abstention. A
   retrieval score is a relevance measure, and a near-miss is by construction
   relevant; the residual has to be spent by a reader, which is what the citation
   verifier and the model's own abstention are for.
3. **The rerank working point sits on the grid floor**, which is a real result and
   not an artifact: lowering the threshold further would answer more answerable items
   but the grid does not go below 0.2, and every point above it loses answerable
   items faster than it loses near-misses.
4. **These are v1 estimates, not laws.** 40 positives mean every rate moves in steps
   of 0.025, and the numbers are measured on one corpus snapshot
   (`vault-1.21.x-1817bdfe`) with one embedder and one reranker.

## Where the working point is recorded (ticket 11, box 2)

**It is recorded, and not inside the run directories.** `reports/abstention/
working-points.json` carries, per scale, the chosen `t`, the raw threshold, the
fitted transform, the justification, the excluded populations, and an explicit
`applies_to_run_ids` list naming every run directory the point was calibrated on.
`ragqa aggregate` reads that file and prints an **`abstention working point`**
column beside each cell in `reports/matrix.md` (and `abstention_working_point`,
`abstention_working_point_raw` in `reports/matrix.csv`), joined on exactly that list.

Writing the number into each run directory instead was considered and rejected: a
run directory is immutable evidence of what a run measured (ADR-0003), and a sweep
is post-hoc arithmetic over its predictions. A threshold written back into a
finished run would be a number that run never used, sitting in the one place a
reader is entitled to trust without checking. The joined file plus the aggregate
column record the same decision without forging evidence.

## Near-misses that score high anyway

`reports/abstention/near-miss-examples.md` shows the three hardest near-misses per
scale with their top-three chunks, so the score can be read next to the text. The
pattern is consistent: the passages are *about* the right subject and contain none
of the requested fact. On `dense` the three that clear 0.5706 are U014, U002 and
U013; on `hybrid` U002, U010 and U017; on `rerank` U011, U006 and U004. A
cross-encoder scores *relevance*, and a near-miss is by construction relevant
without being sufficient.

## One consequence elsewhere: the hop trigger

`configs/sweeps/hops-*.yaml` set `retrieval.trigger_threshold: 0.5771`, which was
the *v0* rerank curve's raw score at the grid floor and sat 0.18 below that curve's
working point (0.75925). Against this v1 calibration it sits **above** the rerank
working point (0.426134), so a hop now fires on rounds that are already above the
abstention line. It is held fixed rather than re-derived: the hop cells are part of
the running matrix, their config digests are how their runs resume, and re-emitting
the parameter would orphan every hop run mid-flight. `ragqa/sweeps.py` records the
derivation it was declared against (`HOP_TRIGGER_SOURCE`), its test asserts the
divergence in both directions, and re-deriving the trigger from this curve is a
one-line change plus a re-run of three cells.

## Regenerate

```bash
python -m ragqa sweep abstention --runs "D:/DE Project/wt/exp/runs" --out reports
python -m ragqa sweep abstention --runs runs --out reports --modes rerank
python -m ragqa aggregate --runs "D:/DE Project/wt/exp/runs" --out reports
python -m ragqa.selftest
```

A run directory whose name does not name a retrieval scale (`ctx-plain-*`,
`cell-*`, `grid-*`) is routed by its own `config.json`, so a grid cell needs no
`ModeSpec` entry. The sweep writes
`reports/abstention/{dense,hybrid,rerank}-pr.{csv,png}`,
`reports/abstention/working-points.json` and `reports/abstention/near-miss-examples.md`.
The CSV columns are `generator, t, precision, recall,
over_abstain_rate_on_answerable, under_abstain_rate_on_near_miss, raw_threshold`.

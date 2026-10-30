# Sensitivity sweeps (ticket 13)

Three dose-response curves, ten configuration files, one command. Each curve is a
one-parameter family measured around the same operating point — the cell
`configs/grid/cell-recursive_parent_child-rerank-plain.yaml` — so a difference
between two points is attributable to the swept parameter and to nothing else
(ADR-0003).

| curve | swept key | points | cells |
|---|---|---|---|
| depth | `retrieval.k` | 5, 10, 20, 40 | `configs/sweeps/k-05.yaml` … `k-40.yaml` |
| chunk size | `chunk.size` | 256, 512, 1024 | `configs/sweeps/chunk-256.yaml` … `chunk-1024.yaml` |
| hops | `retrieval.hops` | 1, 2, 3 | `configs/sweeps/hops-1.yaml` … `hops-3.yaml` |

## How to run it

```bash
python -m ragqa.selftest                        # 115 tests, no network, no GPU
python scripts/run_sweeps.py --emit             # write configs/sweeps/*.yaml
python scripts/run_sweeps.py --check            # the gate: one-parameter diffs, depth >= k
python scripts/run_sweeps.py --dry-run          # projection only; spends nothing
python scripts/run_sweeps.py                    # execute the pending points (resumable)
python scripts/run_sweeps.py --curve all        # reports/sweeps/{k,chunk,hops}.{csv,md,png}
```

`python -m ragqa sweep emit|check|run|curve` is the same code through the package
entry point. The runner resumes: a point whose `runs/<run_id>/metrics.json` exists
for the same configuration digest is skipped, so an interrupted sweep does not
re-spend on what already ran.

## What every cell holds constant, and why

- **The same 40-item item set.** `golden.limit: 40` in all ten cells, because
  spec.md rows 2-4 measure each sweep over the 40 answerable items rather than the
  full 60-item Golden QA Set. The golden file lists answerable items (`A###`)
  before near-misses (`U###`), and `sweeps.check` refuses a limit whose selected
  items are not all answerable — the subset is verified, not assumed.
- **The same corpus, embedding model, index, reranker truncation, generator and
  prices** as the reference cell. `check` asserts that no cell differs from the
  sweep base outside its own parameter.
- **`retrieval.k = 10` outside the depth curve**, so the chunk and hop curves are
  not secretly also depth curves.

### Rule 1 — candidate depth is at least k (ADR-0011)

`rerank_top = max(k, 12)`, so the depth curve reads 12, 12, 20, 40. At k = 20 and
k = 40 the reference's depth of 12 would have deleted candidates the metric is
asked to count, and recall@k would have measured truncation instead of retrieval —
the exact failure ADR-0011 documents. `sweeps.check` reports an `ADR-0011`
violation and exits non-zero if a hand-edited file drops the depth below k.

### Rule 2 — the chunk curve moves resolution, not shape

Overlap keeps the reference ratio `64/512 = 1/8` (32, 64, 128) and the parent
budget keeps the reference ratio `1024/512 = 2` (512, 1024, 2048), so the child
chunk stays half a parent at every point. Two honest remarks about this cell:

- `chunk.overlap` is carried for consistency and for the closed config schema (it
  must be smaller than `chunk.size`), but `recursive_parent_child` chunking does not
  consume it — `chunk_recursive` takes `size` and `parent_size` only. In this curve
  the child budget and the parent budget do the work.
- `embed.max_seq_length` is 1024 tokens in every cell, inherited from the reference.
  A 1024-word child can exceed 1024 tokens, so the `chunk-1024` point embeds a
  truncated view of its text. That point's numbers are therefore a *lower bound* on
  what a 1024-word chunk can retrieve, and the report must say so rather than read a
  plateau as evidence that more context never helps.

### Rule 3 — the hop trigger is a different number from the abstention point

The measured rerank working point is **raw 0.75925** (t = 0.4471) in
`reports/abstention/working-points.json`, fitted on the 20 items of the runs it
names (`real-rerank-20261030T092425-8d738820`, `…093154-2ebd65d2`,
`…095541-a6eb2d5e`; only the last contributed retained rows). That is the
*abstention* point: at or above it, the calibration says the round's evidence was
sufficient, and it is the wrong trigger for another round, which has to fire before
the system gives up rather than at the moment it does.

The trigger in all three hop cells is **`retrieval.trigger_threshold = 0.5771`**,
the raw score at t = 0.2 — the floor of the same 18-point curve
(`reports/abstention/rerank-pr.csv`, row 1, `raw_threshold = 0.5771`), obtained from
the fitted transform in `working-points.json`
(`fitted_mean = 0.793426`, `fitted_stdev = 0.256976`):

    raw = 0.793426 + 0.256976 × Φ⁻¹(0.2)
        = 0.793426 + 0.256976 × (−0.841621)
        = 0.577143  →  0.5771

Why there, and not the working point:

- Every one of the 10 answerable calibration items scored above 0.75925, hence above
  0.5771 too: nothing the calibration measured as answerable sits below the trigger,
  so a rewrite is never spent on a round that had already succeeded.
- Only 6 of 10 near-misses clear 0.5771 (`under_abstain_rate_on_near_miss = 0.6` at
  t = 0.2). A top score below it is below the band that even topically adjacent,
  unanswerable questions reach — a round that produced nothing resembling any
  observed answer is the runtime definition of "plausibly failed".
- It sits 0.182 below the abstention point, so the loop spends strictly under the
  calibrated line: a question hops = 1 would have answered is never rewritten, and
  ΔRecall is attributable to the loop rather than to a moved threshold.
- It is identical in `hops-1`, `hops-2` and `hops-3`. Only the cap differs, so the
  curve measures the cap and not the trigger.

Consequence of the trigger being below the answer gate (0.75925): a fused round can
stop as `hit_after_rewrite` on a score between 0.5771 and 0.75925 and still be
abstained on by the generator. The stop reason records which round produced the hit;
the abstention decision is read from `metrics.json`, never inferred from the stop
reason. ADR-0016 governs both: `score` stays on the cross-encoder scale and
`fusion_score` only orders, so the trigger and the abstention threshold read the
same units at every hop.

## The three curves, in words

**Depth (`k`).** *Expected shape, stated before the numbers:* recall@k climbs while
the retriever still misses evidence it could have found with a wider net, then
flattens once the misses are misses at any depth. The curve saturates at the first
point after which recall@k and citation recall do not move beyond the run-to-run
noise — and because the depth is reported next to the metric (ADR-0011), a plateau
cannot be explained away as truncation. Cost rises with depth twice: more candidates
to rescore, and more context tokens in the prompt (`llm.context_chunks = 8` caps
the generator's view, so the second cost is flat while the first is not).

**Chunk size.** *Expected shape:* small chunks sharpen the match and starve the
generator; large chunks do the reverse. Citation precision should peak before
citation recall does, and the crossing of the two is where the curve stops paying.
Read it together with the truncation caveat above: if `chunk-1024` under-performs,
the first hypothesis to rule out is embedding truncation at 1024 tokens, not the
idea of larger chunks.

**Hops.** *Expected shape:* the second round recovers the questions whose first
round put nothing above 0.5771; the third recovers little more while still paying a
rewrite call and a second extra retrieval. The report needs the stop-reason
histogram, not just the metric: `hit_first_round` / `hit_after_rewrite` /
`cap_reached` / `abstained` per hop, plus `mean_hops`, is what shows *why* a hop did
or did not pay.

## The number the report needs: at which hop the loop stops paying

The rule, fixed before the numbers were seen, is a marginal-cost reading, and it is
computed by `sweeps.break_even_hop` from the three finished run directories:

    marginal price of hop h  =  (¥/1k at h − ¥/1k at h−1)
                                ÷ (recall@k at h − recall@k at h−1)

    the loop stops paying at the first hop h ≥ 2 whose marginal ¥ per recall point
    is ≥ the marginal price of hop h−1, or whose recall gain is zero;
    "at which hop" is then h − 1.

Both ¥/1k values come from `metrics.json → system.cost_per_1k_questions_cny` and
both recall values from `metrics.json → retrieval.recall_at_k` of the named run
directories, which is why the CSV in `reports/sweeps/hops.csv` carries `run_id` in
every row.

Two degenerate cases the rule handles explicitly:

- **The loop never fires** (`hit_after_rewrite = 0` at hops 2 and 3). Then ΔRecall
  is exactly 0 for a positive price, the marginal ¥ per recall point is undefined,
  and the answer is **hop 1**: the bounded loop does not pay for itself on this
  corpus. This is a result, not a failed experiment, and the note says it in one
  sentence rather than softening it.
- **The first extra hop already costs more per recall point than the last unit of
  recall it buys is worth** — the rule then also returns hop 1.

What is knowable now, before the runs, with the arithmetic shown: the loop's *money*
cost is nearly all rewrite tokens, and it is small. A rewrite call is one cheap-model
request with `max_tokens = 200` (`ragqa/agentic.py`) and a prompt of roughly 200
tokens (instruction + question + up to five headings). At the reference cell's
prices (`llm.price_in_usd_per_mtok = 0.15`, `llm.price_out_usd_per_mtok = 0.60`, in
every `configs/sweeps/hops-*.yaml`):

    per rewrite call ≤ 200 × 0.15/10⁶ + 200 × 0.60/10⁶ = $0.00015
    per 1,000 questions   = 1,000 × $0.00015 = $0.15 → ¥1.00  (× 6.67)
    hops = 2 → ≤ +¥1.00 per 1,000 questions
    hops = 3 → ≤ +¥2.00 per 1,000 questions

The extra retrieval costs no hosted money — the embedder and the cross-encoder run
locally — so an extra hop's price is dominated by latency and by the rewrite call. A
hop curve whose Δ¥ is about ¥1 per 1,000 questions but whose ΔRecall is zero is
therefore not "cheap enough to keep": it is a hop that bought nothing at a small but
strictly positive price, and the break-even rule above returns hop 1.

**Status: pending.** No hop cell has a finished run in this worktree, so the table
below is the declaration with every metric marked pending rather than filled with a
plausible-looking number. The rows are in `reports/sweeps/hops.md` (and `.csv`,
`.png`), regenerated by `python scripts/run_sweeps.py --curve hops`; the same file's
"At which hop the loop stops paying for itself" section states the answer once the
run directories exist.

| point | run id | recall@k | citation precision | p50 ms | ¥/1k | stop reasons | ΔRecall | Δcite P | Δp50 | Δ¥/1k |
|---|---|---|---|---|---|---|---|---|---|---|
| hops-1 | pending | pending | pending | pending | pending | pending | — | — | — | — |
| hops-2 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| hops-3 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

## Projection: what the sweep will spend (a count, not a measurement)

From the declaration and `golden.limit: 40` (`python scripts/run_sweeps.py --dry-run`,
which executes nothing). These numbers come from the configuration files and
spec.md rows 2-4, not from a run:

| family | points | generation calls | spec.md row |
|---|---|---|---|
| depth | 4 | 160 | row 2: 4 × 40 |
| chunk | 3 | 120 | row 3: 3 × 40 |
| hops | 3 | 120 | row 4: 3 × 40 |
| **total** | **10** | **400** | 160 + 120 + 120 |

Worst case on top: 120 rewrite calls (hops-2: 40, hops-3: 80), each fired only when
a round's best score is below 0.5771. The real number is read from each hop run's
`hop_stats.json` afterwards.

## Where every number above comes from

| number | source |
|---|---|
| 0.75925 (abstention working point, rerank) | `reports/abstention/working-points.json` → `modes.rerank.raw_threshold`, measured on `real-rerank-20261030T095541-a6eb2d5e` (plus `…092425-8d738820`, `…093154-2ebd65d2`) |
| 0.5771 (hop trigger) | same file's fitted transform applied to t = 0.2; equals `reports/abstention/rerank-pr.csv` row 1 `raw_threshold` |
| 0.793426 / 0.256976 | `working-points.json` → `modes.rerank.transform.fitted_mean/fitted_stdev` |
| 10/10 answerable above, 6/10 near-misses above, at t = 0.2 | `rerank-pr.csv` row 1 (`recall = 1.0`, `under_abstain_rate_on_near_miss = 0.6`) |
| 160 / 120 / 120 generations | spec.md rows 2-4; per-point items from `configs/sweeps/*.yaml` (`golden.limit: 40`) |
| $0.15 / $0.60 per Mtok | `configs/sweeps/hops-*.yaml` → `llm.price_in_usd_per_mtok` / `price_out_usd_per_mtok` |
| ≤ 200 output tokens per rewrite | `ragqa/agentic.py` → `client.complete(..., max_tokens=200)` |

Every metric cell in the curve artifacts names its run directory (`reports/sweeps/*.csv`,
`run_id` column), so any sentence in the report can be traced back to the run that
produced it (ADR-0003).

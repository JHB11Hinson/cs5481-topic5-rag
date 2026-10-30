# Reading the aggregate bundle

`reports/` is generated. Nothing in it was typed by hand, and the command that produced it is the
one in `reports/README.md`:

```
python -m ragqa aggregate --runs "D:\DE Project\wt\exp\runs" --out reports
```

Everything below describes the snapshot in this branch: **2 of 18 matrix cells finished**. The
tables were designed to stay readable while the matrix fills in, so the same command today and
tomorrow produces the same files with fewer `missing` rows.

## What each table answers

| file | the question it answers |
|---|---|
| `matrix.md` | For each of the eighteen cells, what did the configuration score on every headline metric, and which run directory says so? Then: how much does each factor level move the mean, over how many cells, and do the two factors interact? |
| `matrix.csv` / `matrix.json` | The same content for a spreadsheet or for code; the JSON additionally carries the bootstrap intervals, the contrasts, the digest drift and the list of run directories that matched no cell. |
| `significance.md` | How wide is the interval around each cell's number, and is the difference between two factor levels bigger than the pairing noise? Bootstrap intervals resample **items**; McNemar runs on discordant **item** outcomes. |
| `judges.md` | Do the verification layers agree with the thirty hand labels, how do NLI and the LLM judge disagree with each other, and which layer is allowed to gate a reported citation number? |
| `cost.md` | Per cell: prompt and completion tokens by component, money per 1,000 questions, index size, p50/p95 latency. |
| `figures.md` + `figures/*.png` | The k / chunk-size / hop sensitivity curves and the three abstention curves, redrawn from the CSVs ticket 13 and ticket 11 wrote, so a figure cannot drift from its table. |

Three conventions hold across the bundle:

- **Every row carries its run id.** A row that says `missing` carries nothing else: the cell had no
  run directory, or one without `metrics.json`, and it is printed rather than dropped so the table
  always has eighteen rows.
- **Cells are joined by recomputed config digest.** The digest in `configs/grid/grid.json` is stale
  for all eighteen cells (it predates a config default), so it is reported as drift and never used
  as a key. The join recomputes the digest from each cell's YAML, which is the same rule
  `grid.plan()` uses to decide whether a cell is finished.
- **The statistics name their protocol.** Bootstrap: 10,000 resamples, seed `20261030` mixed with
  the cell name, resample unit = item, 95% percentile interval. Paired test: McNemar's exact test,
  two-sided.

## The number I would put in an abstract

> On the 60-item Golden QA Set, the hybrid-retrieval configuration with fixed 512/64 chunks and no
> contextualization returned the evidence chunk inside the top 10 for **90.0% of the 40 answerable
> questions** (95% CI 80.0–97.5) and produced a verified citation for **95.0%** of them, while
> abstaining on **20 of 20** near-misses — at **¥8.46 per 1,000 questions** and a p50 of 39.9 ms.
> Run: `grid-fixed-hybrid-plain-20261030T125429-6170ae66` (`cell-fixed-hybrid-plain`).

The same sentence for the dense cell (`grid-fixed-dense-plain-20261030T124637-8ae4eb06`) is 85.0%
(72.5–95.0) hit@10 and 87.5% citation recall at ¥9.27 per 1,000 — so the one contrast that exists so
far favours hybrid by five points of hit rate and eight of MRR (0.653 vs 0.482), on two cells and
without a paired test. That is a direction, not a result.

## Caveats a reader has to know before quoting a number

1. **The citation numbers are the containment layer, not a judge.** The matrix cells ran with
   `judge_enabled: false` and no judge cost component, so `citation precision 0.9846` means "the
   quoted span occurs in the cited chunk" — a substring check. It does not mean the citation
   supports the claim. `judges.md` reports kappa 0.857 for the judge on the calibration set, but no
   matrix cell used it. Any claim about *faithfulness* needs the judge-enabled runs.
2. **The abstention threshold never fires in these two cells.** The threshold travels with the
   retrieval level (dense 0.20, hybrid 0.01, rerank 0.0, from `grid.RETRIEVAL_LEVELS`), and the
   items that actually abstained had top scores well above it — 0.658 against 0.20 in the dense cell,
   0.032 against 0.01 in the hybrid cell. Every abstention in the snapshot is the generator's own
   refusal: all 24 in the dense cell and all 22 in the hybrid cell carry a written `abstain_reason`.
   So `over-abstain rate` and `abstention recall` here measure the generator's judgement, not the
   tuned operating point, and they are not comparable across retrieval levels on a common threshold.
3. **Latency is a cache artefact.** The dense cell served 61 of its 64 LLM calls from `llm.sqlite`
   (17.3 ms p50); the hybrid cell served 36 of 60. A p50 of 17 ms is a cache read, not a network
   round trip, and the hybrid cell's p95 of 7,502.5 ms is one uncached item. The latency columns rank
   cells by cache luck, not by speed; a cold-latency table needs cacheless runs.
4. **Two cells cannot support main effects or interactions.** `matrix.md` prints every level mean
   with the number of cells behind it, and prints `missing` where none exist. The interaction table
   is marked unestimated: every term is zero by construction until four corners of a 2×2 sub-table
   exist. No contrast in `significance.md` has a pair yet, so all of them read `missing` — the
   honest output, and not evidence that the factors are equivalent.
5. **The design had 60 items, so rates move in steps of 1/40 and 1/20.** Hit rate is over 40
   answerable items, abstention recall over 20 near-misses. The intervals are correspondingly wide,
   and two cells differing by one item differ by 2.5 points.
6. **`metrics.json` and the artifacts are recomputed and compared.** Every headline number in the
   matrix is recomputed from `predictions.jsonl` / `citations.jsonl` / `chunks.jsonl`; a
   disagreement with `metrics.json` prints as `DRIFT` and lands in `matrix.json`. The current
   snapshot has zero drift, after one real bug was found this way: `citations.jsonl` stores the
   generator's `-1` span sentinel, so a span counts only when it is non-negative.
7. **`golden/v1.jsonl` is the v1 set (60 items: 40 answerable, 20 near-miss).** The abstention
   working points in `reports/abstention/working-points.json` were fitted on the v0 set of 20 items
   and are carried forward as a starting point; they are the reason the thresholds in caveat 2 look
   inert rather than obviously wrong.
8. **Fifteen cells are absent and one is unfinished.** `matrix.json` lists the run directories that
   matched no cell (`orphan_runs`), the ones with no `metrics.json` (`unfinished_runs`), and any
   unreadable ones. Anything there is a fact about the run root, not about a configuration.

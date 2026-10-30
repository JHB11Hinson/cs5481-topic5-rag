# Report fact-check (ticket 17, final verification pass)

Read-only audit of `reports/report.md` / `report.docx` / `report.pdf` / `slides.pptx` /
`submission.pdf` against the artifacts that produced them (`reports/*`, `notes/*`, and the
live run directories in `D:\DE Project\wt\exp\runs`). No file outside this note and
`SUBMISSION.md` was touched.

Snapshot audited: worktree `17-factcheck` at `2cbd8f2`, `reports/` bundle generated from
`D:\DE Project\wt\exp\runs`, PDFs rebuilt from that bundle. Where the live run directory has
moved on, the verdict says so rather than calling it a defect.

**Staleness policy (read this first).** `reports/` is being regenerated as the matrix
finishes, and the prose will be refreshed after it. Every experiment number in §§3–4 that the
next `aggregate` run will recompute is marked **stale**, listed once in §1.0, and not argued
about. The actionable findings are the ones a regeneration cannot fix: **a claim with no
source at all, a mismatch against an artifact that already exists, a requirement the shipped
docx/pdf does not satisfy, and prose describing behaviour the code does not have** — 9
mismatches, 3 with no source, and 2 requirement gaps (§2 rows 11, 17).

Headline: **75 quantitative claims audited as rows. 61 match, 9 mismatch, 3 have no source,
and the rest are stale because the matrix kept running.** One graded requirement (brief item
1, the chunking comparison) is unmet in the report but is now answerable from runs already on
disk, and one (brief item 5, answer correctness) has no number anywhere in the report or the
artifacts.

### 1.0 What the refresh will fix, and is therefore not a finding

Expected to change under the next `aggregate` + prose pass, recorded once here and not
re-argued below: the finished-cell count and every `missing` row; all main effects,
interactions and contrasts; the §3.5 per-class counts (new cells add failures); the §3.7 cost
and latency table; the §3.2 abstention working points and their denominators (the bundle in
this worktree is still the **golden-v0** sweep — `working-points.json` says `items_in_run: 20`,
`answerable_total: 10` — and the integration bundle replaces it with a 60-item v1 sweep, so
the fitted `t`, the raw thresholds, and the "8 of those 10 near-misses" sentence in §4 all
move); the "2 of 18" framing in §1, §3.8, slides 6/13 and §A.1. Ten of the twelve statements
in §1's second and third paragraphs currently rest on two cells and will be rewritten.

---

## 1. Number audit

Every quantitative claim in the report, its figures, and the slides, traced to the artifact
that produced it. `reports/…` paths are relative to this worktree; `runs/<id>` means
`D:\DE Project\wt\exp\runs\<id>`. Verdicts: **match**, **stale**, **mismatch**, **no source**.

| # | claim (location) | printed | source artifact | value in source | verdict |
|---|---|---|---|---|---|
| 1 | corpus size (§1, §2.1, slide 3) | 1,268 documents, 5.62 M chars | `reports/baselines/window-cost.json` → `corpus` | `documents: 1268`, `total_chars: 5622957` | match |
| 2 | corpus shape (§2.1) | median 1,573, mean 4,434.5 | same, `corpus.p50` / `corpus.mean_chars` | `1573` / `4434.5` | match |
| 3 | heading-bounded probe (§2.1) | 9,444 sections, median 31 words, mean 56–67 at 128/192/256 | `docs/adr/0010-chunks-accumulate-across-headings.md` | "9,444 sections … median of 31 words and a p90 of 163 … mean 56 to 67 words whether the target was 128, 192, or 256" | match (ADR, not a run artifact) |
| 4 | chunks per strategy (§2.1, §A.5, slide 1) | fixed 2,318, recursive 2,203 | `runs/grid-fixed-dense-plain-…8ae4eb06/metrics.json` → `system.chunks_indexed`; `…recursive_parent_child-dense-plain-…5b0e5d3e` | `2318`; `2203` | match |
| 5 | index size (§2.1, §3.7) | 22.9 MiB | `…8ae4eb06/metrics.json` → `system.index_bytes` | `23966243` = 22.86 MiB | match |
| 6 | embedder (§2.2) | bge-m3, 1,024 dims, 8,192-token window | `…6170ae66/models.json`; `ragqa/embed.py:125` (`get_sentence_embedding_dimension`) | `BAAI/bge-m3`; dim read from the model | match (note: `embed.dim: 256` in `config.json` is the **stub** embedder, `embed.py:360` — a grader diffing configs will ask) |
| 7 | late chunking geometry (§2.2) | 2,048-token windows, 256 overlap | `docs/adr/0015-late-chunking-windows.md`; `configs/grid/*.yaml` `context.window_tokens/window_overlap` | `2048` / `256` | match |
| 8 | whole-document probe (§2.2, §2.5) | 5.56 GB of 6.00 GB; 53 k-char doc truncated | ADR-0015 | "peak 5.56 GB of a 6.00 GB card", "a 53 k-char document truncated at 8,192 tokens" | match |
| 9 | candidate floor (§2.2) | `rerank_top = max(k, 12)`, k=10 | `runs/…6170ae66/config.json`; `ragqa/grid.py:111` | `retrieval.rerank_top = 12`, `retrieval.k = 10` | match |
| 10 | golden strata (§2.4 table) | 10 / 8 / 8 / 8 / 6 = 40, +20 | `golden/v1.jsonl` `type` | `fact_lookup 10, param_value 8, table_content 8, multi_hop 8, concept 6, near_miss 20` | match |
| 11 | answerable difficulty (§2.4 table) | easy 6, medium 23, hard 11 | `golden/v1.jsonl` (`answerable: true`) | 6 / 23 / 11 | match |
| 12 | **near-miss difficulty (§2.4 table)** | **easy 4, medium 11, hard 5** | `golden/v1.jsonl` (`answerable: false`) | **easy 4, medium 10, hard 6** | **mismatch** |
| 13 | total difficulty (§2.4 table) | easy 10, medium 33, hard 17 | `golden/v1.jsonl` all rows | 10 / 33 / 17 | match — but row 12 makes the printed column sum to 34 medium against a stated 33 |
| 14 | five near-miss generators (§2.4) | 5 kinds | `golden/v1.jsonl` `tags` on near-misses | `version-drift, deployment-specific, sibling-product, undocumented-combination, commercial` | match |
| 15 | bootstrap protocol (§2.4, §A.1, slide 5) | 10,000 resamples, seed 20261030, unit = item | `reports/matrix.json` → `protocol` | `bootstrap_resamples 10000`, `bootstrap_seed 20261030`, `resample_unit item` | match |
| 16 | power arithmetic (§2.4, slide 5) | 60 answerable → ~12 discordant, 10:2 p≈0.04; 24 → ~5, p≈0.38 | exact two-sided binomial over the printed split | 0.0386; 0.375 | match (self-consistent) |
| 17 | matrix status (§1, §3.1, slide 6) | 2 finished, 1 unfinished, 15 absent / "16 print missing" | `reports/matrix.md` header | "18 declared, 2 finished, 1 unfinished, 0 unreadable, 15 absent" | **stale** — the live root now has **8 finished** grid runs (`grid-fixed-dense-plain`, `-hybrid-plain`, `-dense-contextual_prefix`, `-hybrid-contextual_prefix`, `-rerank-plain`, and the three `recursive_parent_child-*-plain`), 1 unfinished (`grid-fixed-rerank-contextual_prefix`, no `metrics.json`), 9 absent |
| 18 | digest bookkeeping (§3.1) | zero digest drift, zero orphan, zero unreadable | `reports/matrix.json` → `drift` / `orphan_runs` / `unreadable_runs` | all `[]` | match narrowly — `matrix.md:7` prints "18 cell(s) carry a stale digest in `grid.json`" (`design.digest_drift`, and `stored_digest ≠ config_digest` on all 18 cells); the report never mentions it |
| 19 | dense cell metrics (§3.1 table, §A.1, slide 7) | hit@10 0.8500, MRR 0.4817, nDCG 0.5697, cit.prec 1.0000, cit.rec 0.8750, ¥9.2745 | `runs/…8ae4eb06/metrics.json` | `hit_rate 0.85`, `mrr 0.4817`, `ndcg_at_10 0.5697`, `citation_precision 1.0`, `citation_recall 0.875`, `cost_per_1k_questions_cny 9.2745` | match |
| 20 | hybrid cell metrics (§3.1 table, §A.1, slide 7) | 0.9000, 0.6529, 0.7163, 0.9846, 0.9500, ¥8.4638 | `runs/…6170ae66/metrics.json` | `0.9`, `0.6529`, `0.7163`, `0.9846`, `0.95`, `8.4638` | match |
| 21 | main effects (§3.1 paragraph) | chunk `fixed` 0.8750 over 2 cells; dense 0.8500/1, hybrid 0.9000/1, plain 0.8750/2 | `reports/matrix.md` main effects | identical means and cell counts | match at the snapshot — **stale** the moment the new cells are aggregated (six more finished cells move the chunk, retrieval and contextualisation means and every cell count) |
| 22 | interactions (§3.1) | all interaction terms zero by construction; all nine contrasts `missing` | `reports/matrix.md` Interactions; `reports/significance.md` | 9 contrast rows printing `missing` | match at the snapshot (3 of 9 strata now have both ends) |
| 23 | hybrid−dense deltas (§3.1, slide 7) | +5.0 hit@10, +17.1 MRR, +7.5 cit.rec | rows 19–20 | 0.05 / 0.1712 / 0.075 | match |
| 24 | abstention grid (§1, §3.2, slide 8) | 18 points on [0.2, 0.9] | `reports/abstention/working-points.json` → `protocol.grid` | `points 18, min 0.2, max 0.9` | match |
| 25 | working point hybrid (§3.2 table) | t 0.4059, raw 0.030432, P 0.556, R 1.000, over 0.000, under 0.800 | same → `modes.hybrid` | `0.4059`, `0.030432`, `0.555556`, `1.0`, `0.0`, `0.8` | match |
| 26 | working point rerank / llm (§3.2 table) | t 0.4471, raw 0.759250, P 0.714, R 1.000, over 0.000, under 0.400 (both rows) | same → `modes.rerank`, `modes.llm` | identical values in both modes | match — identical because the `real-llm` run's top score is the cross-encoder's; a one-clause explanation would stop a reader calling it a copy-paste |
| 27 | "would have refused 8 of 10 near-misses" (§4) | 8 of 10 | `modes.hybrid.under_abstain_rate_on_near_miss = 0.8` | 0.8 | match |
| 28 | shipped-threshold failure (§3.2) | 0.20 abstained on all 20 items of its run | `runs/real-hybrid-20261030T091924-f1742d4e` `metrics.json` + `config.json` | `over_abstain_rate 1.0`, `abstained_answerable 10`, `abstained_unanswerable 10`, `abstain_score_threshold 0.2` | match |
| 29 | hybrid score lattice (§3.2, slide 8) | 2 answerable + 5 near-misses at 0.032522; 5 answerable at 0.032787; gap 0.000265; scale 0.0164–0.0328 | `runs/real-hybrid-20261030T092148-08d22872/predictions.jsonl` (max `retrieved[].score`) | 0.032522 → A007, A009, U001, U005, U006, U007, U010; 0.032787 → A002–A006; Δ 0.000265; min 0.016393, max 0.032787 | match |
| 30 | abstentions with a reason (§3.2) | 24 dense, 22 hybrid | `…8ae4eb06` / `…6170ae66` `predictions.jsonl` | 24 abstained, 0 without reason; 22 abstained, 0 without reason | match |
| 31 | observed abstain scores (§3.2) | 0.658 and 0.032, "far above" 0.20 / 0.01 | same files | dense abstentions span 0.5437–0.7194 (A003 = 0.658185); hybrid span 0.0164–0.0328 (A031/A035 = 0.032018) | match (representative values; both ranges clear the thresholds) |
| 32 | per-level thresholds (§3.2) | 0.20 dense, 0.01 hybrid | `ragqa/grid.py:107-112`; `runs/…6170ae66/config.json` | dense 0.20, hybrid 0.01, rerank 0.0 | match |
| 33 | sweep declarations (§3.3 table) | 4+3+3 points, 40 items, 160/120/120 calls | `configs/sweeps/{k-05,k-10,k-20,k-40,chunk-256,chunk-512,chunk-1024,hops-1,hops-2,hops-3}.yaml` | 10 files; `golden.limit: 40` in each | match |
| 34 | sweep status (§3.3) | 0 of 4 / 0 of 3 / 0 of 3 finished | `reports/sweeps/{k,chunk,hops}.{md,csv}` | every metric pending | match (still true at the live root: no `sweep-*` run directory exists) |
| 35 | hop trigger (§3.3) | `trigger_threshold = 0.5771`, 0.182 below 0.75925 | `ragqa/sweeps.py:55,109`; `configs/sweeps/hops-*.yaml` | `HOP_TRIGGER = 0.5771`, "0.182 below" | match (0.75925 − 0.5771 = 0.18215) |
| 36 | hop rewrite cap (§3.3) | ≤ 200 output tokens | `ragqa/agentic.py:80` | `complete(..., max_tokens=200)` | match |
| 37 | hop price (§3.3) | about ¥1.00 per 1,000 for hop 1 | `notes/sweeps.md:171-173` | "= $0.15 → ¥1.00 (× 6.67)"; "hops = 2 → ≤ +¥1.00" | match |
| 38 | judge table (§3.4, slide 4) | 0.667/0.833/0.933 agreement; P 0.667/0.826/1.000; R 1.000/0.950/0.900; κ 0.000/0.595/0.857 | `reports/judges.md` | `0.6667/0.8333/0.9333`, `0.6667/0.8261/1.0`, `1.0/0.95/0.9`, `0.0/0.5946/0.8571` | match |
| 39 | layer disagreement (§3.4, slide 4) | five `nli_only`, none `judge_only` | `reports/judges.md` confusion | `nli_only 5`, `judge_only 0` | match |
| 40 | κ standard error (§3.4) | about ±0.18 at n = 30 | derived from `judges.md` counts (Fleiss SE) | NLI: po 0.8333, pe 0.5888 → SE 0.166; judge: SE 0.098 | match (the ±0.18 is the NLI figure, which is the layer the sentence is about) |
| 41 | judge calibration cost (§3.7) | ¥0.0436 for 30 calls | `notes/judge-calibration.metrics.json` → `cost.cny` | `0.0435587685` | match |
| 42 | **cost per 1,000 claims (§3.7, slide 4)** | **"about ¥0.15 per 1,000 claims"** | same file: `cost.cny / calibration_set × 1000` | **0.0435588 / 30 × 1000 = ¥1.452** | **mismatch (10×)** |
| 43 | judge misses (§3.4) | two false negatives: a chain compression, a sentence at the end of a long chunk | `notes/judge-calibration.md:186-188` | "both false negatives on true claims … very end of a long chunk (C-A006-c3)" | match |
| 44 | failure count (§3.5, §4, slide 9) | 14 failures from 18 candidates | `notes/error-taxonomy.md` | 14 rows, "18 failure candidates" | match |
| 45 | class counts (§3.5 table) | 4/2/2 · 2/2/1 · 1/1/0 · 0/1/1 · 1/0/0 · four empty classes · totals 8/6/14 | `notes/error-taxonomy.md` "Counts per class per cell" | identical | match |
| 46 | baseline cells (§3.6) | four comparison cells | `scripts/run_baselines.py` `CELLS`; `configs/baselines/` | 4 entries (`closed-book`, `long-context`, `embed-minilm`, `gen-cheap`) | match |
| 47 | long-context vs reference (§3.6, slide 11) | ¥4.77 vs ¥9.54 per 1,000 | `reports/baselines/window-cost.json` → `shapes` | `long_context_20000: 4.7682`, `retrieval_k10_8chunks: 9.5366` | match |
| 48 | no-truncation row (§3.6) | ¥5.28 | same → `long_context_70000` | `5.2791` | match |
| 49 | prompt shape (§3.6) | 6,897 tokens vs 2,131, mean doc 4,435 chars | same → `shapes.*.prompt_tokens_mean`, `corpus.mean_chars` | `6897.4` / `2131.4` / `4434.5` | match |
| 50 | projection error (§3.6) | reproduces the measured prompt to within 8% (6,897 vs 7,479) | same → `measured_tokens_in_mean` | `7478.9`; error 7.79% | match |
| 51 | **"cannot close a 3× gap" (§3.6, slide 11 notes)** | **3×** | same → 9.5366 / 4.7682 | **2.00×** | **mismatch** (the prompt-token ratio is 3.2×, the cost ratio the sentence is about is 2.0×) |
| 52 | generator probe volume (§3.6) | nineteen requests across **twelve** models, $0.0017 | `reports/baselines/generator-probe.json` | `probe.attempts: 19`, `total_spend_usd_all_attempts: 0.001699`, **13 candidate models** | **mismatch** (12 vs 13) |
| 53 | generator swap (§3.6, slide 11 notes) | gpt-6-luna $0.001019 vs $0.001430 → ¥6.80 vs ¥9.54, 29% saving | same → `candidates` | `gpt-6-luna 0.001019 / 6.797`; `deepseek-v4.1-flash 0.00143 / 9.5366`; saving 28.7% | match (`chosen: gpt-6-luna` agrees) |
| 54 | token totals (§3.7 table) | 415,147 / 35,261 and 387,766 / 29,952 | `metrics.json` → `system.cost_components.generation` | identical | match |
| 55 | money (§3.7 table) | ¥0.5565 / ¥0.5078, ¥9.2745 / ¥8.4638 | same → `cost_cny`, `cost_per_1k_questions_cny` | identical | match |
| 56 | latency (§3.7 table, §A.1) | 17.3 / 21.3 and 39.9 / 7502.5 ms | `timings.json` → `p50_ms`, `p95_ms` | `17.305/21.252`, `39.944/7502.514` | match |
| 57 | cache split (§3.7, slide 12) | 61 of 64 and 36 of 60 LLM calls cached | `cache_stats.json` | `llm_cache_hits 61, misses 3`; `hits 36, misses 24` | match |
| 58 | prefix economics (§3.7) | warm-up ¥0.373; rerun ¥0.000 with 2,203 hits | `notes/prefix-stats/{warmup,rerun}.json` | `cost_cny 0.37298`; `cost_cny 0.0, cache_hits 2203, chunks 2203` | match (the "identical strings" half is not evidenced by these two files — they record counts, not a diff) |
| 59 | retrieval vs non-retrieval split (§4) | ten of fourteen are retrieval | `notes/error-taxonomy.md` | 6 + 4 = 10 | match |
| 60 | **"five failures total" for the rest (§4)** | **five** | same | 2 over-abstentions + 1 fabricated span + 1 parse failure = **4** | **mismatch** |
| 61 | **"A010 and A030 fail the same way in both cells" (§4)** | both cells | `…6170ae66/metrics.json` → `retrieval.misses`; `notes/error-taxonomy.md` rows 2 and 10 | hybrid misses are `A015, A030, A035, A038` — **A010 is not a hybrid miss**; A030 fails in both, A010 in the dense cell only | **mismatch** |
| 62 | "one fabricated citation out of **47** containment-checked claims" (§4) | 47 | `…8ae4eb06/citations.jsonl` = 73 rows; `…6170ae66/citations.jsonl` = 65 rows (1 failure) | 138 claims across the two cells, 1 `quote_not_in_chunk`; no artifact prints 47 | **no source** |
| 63 | span −1 (§4, §A.5) | A032's claim carries span `-1` | `…6170ae66/citations.jsonl` | `A032-c2` has `span_start = span_end = -1` | match |
| 64 | **citation-precision denominator (§A.1)** | **"precision for the dense cell is reported over 35 claims"** | `…8ae4eb06/metrics.json` → `citations.claims` | **73 claims** (over 35 *items*; 35 is the recall numerator, 35/40 = 0.875) | **mismatch** |
| 65 | interval table (§A.1) | hit@10 [0.7250, 0.9500] etc. | `reports/significance.md` | identical to 4 dp | match |
| 66 | golden authoring (§A.4) | 49 evidence quotes, all distinct; six items changed | `golden/v1.jsonl`; `notes/golden-v1-authoring.md:68` | 49 quotes, 49 distinct; "Six items changed" | match |
| 67 | demo (§A.5, slide 10) | 38.9 s load, 2,203 chunks; near-miss at 0.669 | `notes/demo-script.md:21,28,179` | "38.9 s, 2,203 chunks"; "best chunk scored 0.669" | match |
| 68 | page counts (title, §A.2) | 9 report pages, 14 slides, 23 submission | `reports/report.pdf`, `slides.pdf`, `submission.pdf` | 9 / 14 / 23 | match |
| 69 | main-content limit (§A, brief) | 6 pages | `reports/report.pdf` page 6 | `5 References` heading at y = 504 of 842 on page 6; Discussion ends above it | match |
| 70 | sub-answers in slides | "17 ADRs", "9 error classes", "3 retrieval levels", "2 chunk strategies", "60 items" | `docs/adr/` (17 files), taxonomy, `grid.py`, `golden/v1.jsonl` | 17 / 9 / 3 / 2 / 60 | match |
| 71 | **"12 cells after the matrix, plus 3 sweeps and 5 baseline cells" (slide 2)** | 12 and 5 | `scripts/run_baselines.py` `CELLS`; `reports/matrix.md` | 4 baselines, 18 matrix cells; no artifact yields 12 or 5 | **no source** (baseline count is also a mismatch — see #72) |
| 72 | **"all 5 baseline cells" (slide 6)** | 5 | `scripts/run_baselines.py` `CELLS`; `configs/baselines/` | **4** | **mismatch** |
| 73 | abstention fit provenance (§3.2 source line, §4 "8 of those 10") | "fitted on golden v0 (20 items, 10 answerable)" | `reports/abstention/working-points.json` (`sources`, `modes.hybrid.answerable_total`) | `items_in_run: 20`, `rows_retained: 20`, `answerable_total: 10`, `under_abstain… 0.8` | match at this snapshot; **stale** — the v1 sweep moves the point and the denominators, so the two derived sentences need rewriting, not renumbering |
| 74 | rerank and `llm` rows as two measurements (§3.2 table) | two modes, two sets of numbers | `reports/abstention/{rerank,llm}-pr.csv` | **byte-identical** (866 B, SHA-256 `E4D2C029…CDE5`), first row `0.2,0.6250,1.0000,0.0000,0.6000,0.5771` in both | **mismatch (presentation)** — one curve printed as two modes; the integration bundle deletes `llm-pr.csv` for the same reason, so §3.2 keeps a row the bundle no longer carries and §A.2's "Per-mode precision-recall CSVs" overstates it. Needs one clause (the `llm` run scores its top candidate with the cross-encoder, so the curve is the reranker's), not a deletion |
| 75 | dense / cosine operating point (§3.2 prose, §3.3, §3.8) | the sweep normalises "identity for cosine" and the dense cells ship `0.20` | `ragqa/abstain.py:139` (`ModeSpec(mode="dense", transform="identity", prefixes=("dense","cosine"))`); `reports/abstention/working-points.json` → `modes` | the transform exists in code; `modes` holds only `hybrid`, `rerank`, `llm` — no dense run exists under those prefixes, so no dense curve and no calibration for the 0.20 that two headline numbers run under | **no source** for the dense operating point |

### Counts

**75 rows audited: 61 match, 9 mismatch (#12, #42, #51, #52, #60, #61, #64, #72, #74), 3 no
source (#62, #71, #75), 2 stale rows (#17, #73).** Row #17 carries six stale restatements of
the same quantity (§1 twice, the §3.1 table, the §3.1 main-effect paragraph, §3.8, slides 6
and 13). Eight further stale statements are not separate rows: "that pair is the whole of our
measured matrix" (§1), "the other sixteen are `missing`" (§1), "chunk `recursive_parent_child`
unestimated" (§3.1), "one has a run directory with no `metrics.json` (…57be667d)" (§3.1 and
§A.1 row 7 — that run now carries a 1,631-byte `metrics.json`), the "2 of 18" slide title
(slide 6), "Finish the 16 cells" (slide 13), the *Two cells* threat bullet (§3.8), and the
`missing` entries in §A.1 rows 2, 3, 5, 6 and 10–18. Ten stale statements in total, all in
§1.0's expected-to-change set.

Rows 24–31 (the whole abstention table) are marked match **against the v0 bundle in this
worktree**; they join row 73 as stale the moment the v1 sweep lands. They are listed rather
than dropped so the refresh has the trace, not so they get fixed twice.

---

## 2. Requirement audit

`AGENTS.md` and `docs/course-brief/CS5481_Project_2026-1.pdf`, clause by clause. The brief is
the source of truth; where `AGENTS.md` paraphrases it, the paraphrase was checked against the
PDF text, not against the report.

**No material disagreement between `AGENTS.md` and the brief.** Two differences worth
recording: (a) `AGENTS.md` adds project-wide conventions (English everywhere, no hardcoded
keys, `.env.example`) that the brief does not state — team policy, not graded requirements;
(b) `AGENTS.md` keeps the brief's five Topic-5 requirements verbatim in substance, including
"report retrieval hit rate **and** answer correctness", so item 5 below is not an
`AGENTS.md` invention.

| # | clause | evidence | status |
|---|---|---|---|
| 1 | Due 11:59 pm, Tue 24 Nov 2026 | title page reads "24 November 2026"; 2026-11-24 is a Tuesday | met (submission time is the human's) |
| 2 | Group ≤ 8, registered on Canvas by 18 Oct | contribution table has 8 numbered rows, so the roster fits | at risk — registration is not visible in the repo |
| 3 | Submit report + source code via Canvas, 15-min in-class presentation | `reports/submission.pdf` (23 pp); `ragqa/` + `scripts/`; 14 slides with a 15:00 clock in the speaker notes (`notes/report-notes.md`, "Deck timing") | met for the artifacts; the upload and the talk are the human's |
| 4 | Report at least introduction, methodology, experiments, discussions | §1–§4 (`report.pdf` pp. 1–6) | met |
| 5 | Up to 6 pages of main content | references begin on page 6 at y = 504/842; §6 contribution page on page 9; A.1–A.5 on pp. 7–8 | met, ~10.5 cm of slack on page 6 before the Discussion would spill |
| 6 | Unlimited references and appendix | §5 (14 entries, pp. 6–7) + Appendix A (pp. 7–8) | met |
| 7 | Source code as Jupyter Notebook or Python files | `ragqa/*.py` (26 modules), `scripts/*.py` (13), `tests/`, `pyproject.toml` | met |
| 8 | Slides attached at the end of the report | `submission.pdf` pp. 10–23 = the 14 slides, immediately after the contribution page | met |
| 9 | Contribution statement + ratios (%) + **signature of every member** on a **separate last page of the main report**, immediately before the slides, outside the 6-page count | `report.pdf` p. 9 is `6 Individual Contributions` alone (839 characters on the page, table starts at the top); p. 10 is the slide title | **at risk** — see below |
| 10 | Missing page or missing signature = desk rejection | same | at risk |
| 11 | R1 Data preparation: load, chunk, embed; **compare ≥ 2 chunking strategies and report their impact on retrieval quality** | corpus/chunking/embedding: met (1,268 docs → 2,318 / 2,203 chunks, bge-m3, ADR-0007/0008/0009/0010). The comparison: §3.1 prints `recursive_parent_child` as unestimated and §3.3 says the size curve has no measured number | **not met in the report — but measurable now** (see finding F1) |
| 12 | R2 Storage in a vector database | Qdrant, dense + sparse, one collection per snapshot, 2,318 chunks / 22.9 MiB (`metrics.json`, §2.2) | met |
| 13 | R3 Retrieval: embed the question, retrieve by semantic similarity | three levels at k = 10; dense hit@10 0.8500, hybrid 0.9000, per-cell misses listed | met |
| 14 | R4 Grounded generation, per-claim citation with doc **and chunk**, explicit "not in the KB" | JSON claim contract with `doc_id`/`chunk_id`/span/quote (§2.3), containment in `verify.py`, abstention with a written reason on 24/24 and 22/22 (§3.2) | met |
| 15 | R5 Test set ≥ 20 QA pairs | 60 items (40 answerable + 20 near-misses), `golden/v1.jsonl` | met (3× the minimum) |
| 16 | R5 **retrieval hit rate** | hit@10 with bootstrap CIs, §3.1/§A.1 | met |
| 17 | R5 **answer correctness** | no correctness or accuracy metric exists: `metrics.json` has hit/MRR/nDCG/citation/abstention only, `GLOSSARY.md:83` lists "correctness, accuracy" under *Avoid*, `ragqa/` has no `correctness` symbol, and the report never prints one | **at risk — nothing to point a grader at** (finding F2) |

### The contribution page, specifically

- **Exists:** yes — `report.md` §6 / `report.docx` table 12 / `report.pdf` p. 9.
- **Separate last page of the main report:** yes. Page 9 contains only the heading, the table,
  the confirmation sentence and the representative line; page 8 ends in Appendix A.5.
  `submission.pdf` p. 9 = contribution page, p. 10 = first slide, so it is the page right
  before the appended slides.
- **Outside the 6-page count:** yes — it is page 9, and the main content ends on page 6.
- **A row and a signature line for every member:** 8 rows, each with `[MEMBER n]`,
  `[CONTRIBUTION]`, `[ %]` and its own `______________________________` signature line; a
  `Total` row prints `100 %`; a representative line and a date line follow the table.
- **Do the ratios sum to 100%?** The *Total* row prints 100%, but every individual ratio is
  still `[ %]`. Nothing sums yet, so the page is structurally complete and substantively
  empty. A grader reading it as submitted sees a template.

---

## 3. Consistency audit

The same quantity printed twice, plus three claims about behaviour checked against `ragqa/`.

| quantity | printed where | value A | value B | agree? |
|---|---|---|---|---|
| golden set size | §1, §2.4, §3.1, §A.4, slides 1 and 5 | 60 | 60 | yes |
| corpus size | §1, §2.1, slide 3, `window-cost.json` | 1,268 docs / 5.62 M chars | 1,268 / 5,622,957 | yes |
| chunk counts | §2.1, §A.5, slide 1, `metrics.json` | 2,318 / 2,203 | 2318 / 2203 | yes |
| finished cells | §1, §3.1, §A.1, slides 6 and 13, `reports/matrix.md` | 2 of 18 | 2 of 18 | yes at the snapshot; **8 of 18 on disk now** |
| abstention counts | §3.2, §4, `notes/aggregate.md`, `predictions.jsonl` | 24 dense / 22 hybrid | 24 / 22 | yes |
| prefix economics | §3.7, `notes/prefix-audit.md`, `prefix-stats/*.json` | ¥0.373, 2,203 hits, ¥0.000 rerun | 0.37298 / 2203 / 0.0 | yes |
| judge kappa | §3.4, slide 4, `reports/judges.md` | 0.000 / 0.595 / 0.857 | 0.0000 / 0.5946 / 0.8571 | yes |
| **baseline cell count** | §3.6 vs slides 2 and 6 | **4** | **5** | **no** |
| **long-context gap** | §3.6 vs slide 11 notes vs `window-cost.json` | **3×** | **2.0×** (9.5366 / 4.7682) | **no** |
| **judge cost per 1,000 claims** | §3.7 and slide 4 vs `judge-calibration.metrics.json` | **¥0.15** | **¥1.45** | **no** |
| failure total | §3.5, slide 9, taxonomy vs §4 prose | 14 | 14, but "ten … plus five" = 15 | **no, internally** |
| golden difficulty | §2.4 table: near-miss row vs its own total row | medium 11 + 23 = 34 | stated total 33 | **no, internally** |
| page counts | `notes/report-notes.md` vs the PDFs | 9 / 14 / 23 | 9 / 14 / 23 | yes |
| §A.1 row 7 label | §A.1 vs `reports/matrix.md` row 7 | "unfinished, no `metrics.json`" | `missing` | label differs (the §A.1 wording is the more informative one, and the run now has a `metrics.json`) |
| digest bookkeeping | §3.1 vs `reports/matrix.md:7` | "zero digest drift" | "18 cell(s) carry a stale digest in `grid.json`" | narrowly compatible, but the report should carry the caveat |

### Behaviour claims vs `ragqa/`

| claim | where | code | verdict |
|---|---|---|---|
| abstention is an explicit, thresholded decision and the matrix abstentions came from the generator, not the threshold | §2.3, §3.2, §3.8 | `ragqa/generate.py:82` `if top["score"] < threshold: return self._abstain(...)`, `:88` same per hit, `:110` `no_claim_could_be_grounded`; observed top scores 0.5437–0.7194 vs 0.20 and 0.0164–0.0328 vs 0.01 | **holds** — the tuned point never fires; every abstention carries a model-written reason |
| the contextual prefix is index-side only and never shown to the generator | §2.2, §2.5, slide 3 | `ragqa/run.py:142` `index_texts = [child["contextual_text"] …]`; `ragqa/retrieve.py:94` returns `chunk["text"]`; `ragqa/generate.py:155` prompts with `hit["text"]`; `context.py:252` builds `contextual_text` | **holds** — the prefix reaches the embedder and not the prompt |
| the judge layer is what would gate the headline citation numbers, and did not run | §2.3, §3.4, §3.8, slide 4 | `ragqa/verify.py:63` `"supported": error_class == ""` (containment only); `ragqa/judges.py:237` ANDs containment with NLI and judge; `judge.enabled: False` and `grounding.judge_judged: 0` in both matrix runs | **holds** — the §3.1 citation columns are containment numbers, exactly as stated |

---

## What to fix before submission, in priority order

**F1 — the brief's chunking comparison (graded, currently unmet, and now cheap).**
Six `recursive_parent_child` cells finished on disk after this report was generated
(`grid-recursive_parent_child-{dense,hybrid,rerank}-plain-*`). With them, the chunk-strategy
contrast the brief asks for exists at all three retrieval levels, paired on the same 60 items:

| retrieval | fixed hit@10 → recursive | fixed MRR → recursive | fixed cit.rec → recursive |
|---|---|---|---|
| dense | 0.8500 → 0.8500 | 0.4817 → 0.4792 | 0.8750 → 0.9000 |
| hybrid | 0.9000 → 0.9000 | 0.6529 → 0.6521 | 0.9500 → 1.0000 |
| rerank | 0.9000 → 0.9000 | 0.6044 → 0.5985 | 0.8750 → 0.9000 |

That is a clean, reportable null on retrieval quality with a small citation-recall gain — and
it answers brief item 1 instead of deferring it. Regenerate `reports/` from
`D:\DE Project\wt\exp\runs` and rewrite §1 ("That pair is the whole of our measured matrix"),
§3.1 (table, main effects, interactions, contrasts), §3.5 (new failure rows land first in
`notes/error-taxonomy.md`) and slides 6, 9, 13.

**F2 — brief item 5's "answer correctness" has no number.** The report measures hit rate,
MRR, nDCG, citation containment and abstention; nothing is labelled correctness, and
`GLOSSARY.md:83` actively avoids the word. Add one explicit sentence and one number — the
cheapest honest one is already in the artifacts: answer correctness proxied by the hand
taxonomy — "no hand-assigned failure" over the 60 items, currently 52/60 in the dense cell and
54/60 in the hybrid cell, recomputed from `notes/error-taxonomy.md` after the refresh — stated
as a proxy for correctness, not as correctness. Without it the map in §1 ("the brief's five
requirements map one-to-one") overclaims on item 5.

**F3 — the nine wrong numbers a grader can compute in ten seconds.** In one pass:
`¥0.15 per 1,000 claims` → **¥1.45** (§3.7, slide 4); `3× gap` → **2×** (§3.6, slide 11
notes); `five failures total` → **four** (§4); `35 claims` precision denominator → **73
claims over 35 items** (§A.1); `47 containment-checked claims` → **65 in the hybrid cell
(73 dense, 1 failure)** (§4); near-miss difficulty `4/11/5` → **4/10/6** (§2.4 table, which
also fixes the 34-vs-33 column sum); `twelve models` → **13** (§3.6); `A010 and A030 fail the
same way in both cells` → **A030 only; A010 is a dense-cell miss** (§4); slides `5 baseline
cells` → **4** and drop the unsourced `12 cells after the matrix` (slide 2, 6).

**F4 — the contribution page is a template.** Fill `[MEMBER n]` / `[CONTRIBUTION]` / `[ %]`,
make the ratios sum to 100%, delete unused rows, print it and have **every** member sign their
own row, then rebuild and re-confirm page 9 sits immediately before the slides. This is the
one desk-rejection risk that no amount of regeneration fixes.

**F5 — refresh the "2 of 18" framing and its dependants** (§1 ×2, §3.1 table and main-effect
sentence, §3.8, slides 6/9/12/13, §A.1's `missing` rows and its "unfinished … `125648-57be667d`"
row, which now has a `metrics.json`). Do this after F1 so the prose is written once.

**F6 — two small honesty additions, no new numbers.** (a) Say in §3.1 that all 18 cells carry
a stale digest in `configs/grid/grid.json` while every join is recomputed from the cell YAML —
`matrix.md:7` prints it and the report does not. (b) In §3.2, one clause on why the rerank and
`llm` rows of the working-point table are identical (both score the top candidate with the
cross-encoder), so it does not read as a copy-paste.

**F7 — the abstention section describes two things its bundle cannot show.** Neither is fixed
by regenerating; both are prose. (a) `reports/abstention/{llm,rerank}-pr.csv` are
byte-identical here and the integration bundle drops the duplicate, so the §3.2 `llm` row
rests on `working-points.json` alone and §A.2's "Per-mode precision-recall CSVs" overstates
the directory — one clause that the `llm` run's curve *is* the reranker's score, and "per-mode
CSVs" → "the curves for the modes that have runs". (b) The prose promises an `identity`
transform "for cosine" but no dense run exists under the sweep's mode prefixes, so the `0.20`
both headline cells ran under has no calibration artifact — name it as the one uncalibrated
threshold in §3.2/§3.8, or put a `real-dense` run through `ragqa sweep abstention`.

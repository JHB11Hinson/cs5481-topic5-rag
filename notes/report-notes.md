# Report and slides — build notes, page count, and what must be refreshed

Ticket 17. Everything in this note is about the graded deliverables, not about the
experiment. Sources of truth, in order: `reports/report.md` (prose) →
`reports/report.docx` (rendered) → `reports/report.pdf` → `reports/submission.pdf`
(report pages + slides appended).

## Page count, measured

| Artifact | Pages | Notes |
|---|---|---|
| `report.docx` / `report.pdf` | 9 | main content 6, references + appendix 3 |
| `slides.pptx` / `slides.pdf` | 14 | 15-minute structure, demo at minute nine |
| `submission.pdf` | 23 | 9 report pages, then the 14 slides |

**Main-content page count: 6** — title block, §1 Introduction, §2 Methodology,
§3 Experiments, §4 Discussion. Section `5 References` begins on page 6 at y = 504/842,
so the main content ends on page 6 and the references start on that same page; the
limit is not exceeded but there is only ~10 cm of slack on page 6. Verified by
converting the DOCX to PDF and locating the section headings in the PDF text, not by
estimating from word counts:

```bash
python .scratch/topic5-rag/md_to_docx.py reports/report.md reports/report.docx
"D:/DeepSeek Harness/resources/runtime/primary-runtime/dependencies/node/bin/node.exe" \
  "D:/DeepSeek Harness/resources/app/dsh/node_modules/@deepseek-ai/libreoffice-kit/lib/cli.js" \
  convert --input reports/report.docx --output reports/report.pdf
python .scratch/topic5-rag/build_slides.py
# same convert command on reports/slides.pptx -> reports/slides.pdf
python .scratch/topic5-rag/merge_pdf.py       # -> reports/submission.pdf
```

The contribution page (§6) is the last page of the report — page 9 — and the slides
start on page 10, so the required page is the page immediately before the appended
slides.

## Page budget, if text is added

Page 6 holds roughly 10 cm of free space after the Discussion. The matrix table in
§3.1 is currently five rows because fifteen cells share the same `not yet measured`
state; when those cells finish, the two merged rows expand to fifteen, which adds
about 3.5 cm. That fits, but a second addition of similar size would push the
Discussion onto page 7 and break the limit. If the refresh needs more room, shrink
`FIGURE_CM` in `md_to_docx.py` (12.4 cm now) before cutting content.

## What is measured and what is projected

**Measured** (a run directory, a live response, or a hand count over artifacts):

- both matrix cells: `grid-fixed-dense-plain-20261030T124637-8ae4eb06`,
  `grid-fixed-hybrid-plain-20261030T125429-6170ae66` — every metric, token count,
  index size and latency in §3.1 and §3.7.
- the abstention curves and working points, fitted on `real-hybrid-*`,
  `real-rerank-*`, `real-llm-*` (`reports/abstention/*`), 18 of 18 points per mode.
- judge calibration: 30 hand-labelled claims, three layers, κ and confusion grids.
- the generator probe: 19 live requests, $0.0017 total (`reports/baselines/generator-probe.json`).
- the error taxonomy: 14 failures, hand-assigned from the two runs' `predictions.jsonl`,
  `citations.jsonl` and `chunks.jsonl`.
- the prefix warm-up and rerun economics (`notes/prefix-audit.md`).

**Projected** (arithmetic over a measured run and the corpus, never a run):

- the prompt-shape costs in Figure 4 and §3.6: `tokens = chars × 0.2494`, reproducing
  the measured RAG prompt to within 8% (6,897 projected vs 7,479 measured).
- the three sensitivity curves (§3.3): ten points declared, zero finished. The report
  says so and prints no curve.
- the four baseline cells (§3.6): configured and `--dry-run` verified, none run.
- the hop-loop rewrite cost (≤ ¥1.00 per 1,000 questions per extra hop).

**Stated as missing, never smoothed:** the sixteen matrix cells, the ten sweep points,
the four baseline cells, and 26 of the ticket's 40 hand-inspected failures.

## Numbers that must be refreshed when the 18-cell matrix completes

Regenerate `reports/` first (`python -m ragqa aggregate --runs <runs-root> --out reports`),
then redraw the figures (`python .scratch/topic5-rag/report_figures.py`), then edit prose.

1. **§3.1 matrix table** — the two merged rows (`fixed | any | contextual_prefix,
   late_chunking (6 cells)` and `recursive_parent_child | any | any (9 cells)`) become
   fifteen individual rows; `cell-fixed-rerank-plain` changes from `unfinished` to a
   run id plus numbers.
2. **§3.1 main-effects paragraph** — the mean and cell count per level for chunk
   strategy, retrieval mode and contextualisation, all currently resting on 1 or 2 cells.
3. **§3.1 interaction sentence** — "every interaction term is zero by construction" is
   true only while fewer than four corners of a 2×2 sub-table exist.
4. **§3.1 contrasts sentence** — "all nine factor contrasts print `missing`" becomes the
   actual `b`, `c` and exact p per contrast (`reports/significance.md`), and "This is a
   direction, not a result" must be re-earned or withdrawn.
5. **§1 Introduction, both paragraphs** — "Two of the eighteen cells have finished runs;
   the other sixteen are `missing`" and "That pair is the whole of our measured matrix".
   The four headline numbers in the abstract sentence (90.0%, CI 80.0–97.5, 95.0%,
   ¥8.46, 20 of 20) stay valid: those two runs are immutable. Replace them only if the
   report decides to quote a different cell.
6. **§3.2** — "the tuned threshold never fires inside the matrix" and the two observed
   scores (0.658 vs 0.20, 0.032 vs 0.01) hold for the two finished cells only; re-check
   per new cell, and re-quote the 24 and 22 abstention counts for any cell discussed.
7. **§3.5 error table and Figure 3** — class counts per cell, the `total` row, and the
   shortfall sentence "14 failures … not the 40 the ticket asked for". New rows go into
   `notes/error-taxonomy.md` first; the figure is redrawn from that table.
8. **§3.7 cost table** — one row per finished cell: tokens in/out, CNY total, ¥/1k,
   index size, p50/p95. The cache counts (61 of 64, 36 of 60) are per cell too.
9. **§3.6 baselines and §3.3 curves** — if the four baseline cells or the ten sweep
   points run, both sections change shape: the baseline table exists
   (`reports/baselines/table.md`), the curves get real points, and the two "pending"
   sentences must go.
10. **Appendix A.1** — all three tables (18 rows, the full-metric table, the interval
    table) come straight from `reports/matrix.md` and `reports/significance.md`.
11. **§3.8 threats** — the "Two cells" bullet.
12. **Slides 6, 7, 8, 9** — the "2 of 18" framing, the contrast deltas, the abstention
    caveat and the taxonomy counts, plus their speaker notes.

Nothing else in the report moves: the corpus, index, judge calibration, window costs,
prefix audit and golden-set authoring are all already measured.

## Contribution page — instructions for the group (do not submit without this)

`reports/report.md` ends with **§6 Individual Contributions**, rendered as the last page
of the report (page 9 of `report.pdf`), immediately before the appended slides. It is a
placeholder: names, contributions and ratios are not invented anywhere in this repository.

Before submitting:

1. Replace `[MEMBER 1]` … `[MEMBER 8]` with every member's full name, `[CONTRIBUTION]`
   with one line of what that member actually did, and `[ %]` with the agreed ratio.
   Delete unused rows; the roster may be fewer than eight.
2. Check the ratios sum to 100% (the `Total` row is already 100%).
3. **Every member signs their own row** on the printed page. A page missing any
   signature, or missing entirely, is desk-rejected per the course brief.
4. Fill the group representative line and the date.
5. Rebuild the three artifacts with the commands at the top of this note, then confirm
   the contribution page is still the last page before the slides (`merge_pdf.py` prints
   the page counts).

## Figure provenance

The four figures live in `assets/report/`, not in `reports/`, because `reports/` is
generated by `python -m ragqa aggregate` and hand-written files there would break that
rule. `.scratch/topic5-rag/report_figures.py` draws all four from files that already
exist, so a figure cannot drift from its table:

| Figure | File | Drawn from | Runs |
|---|---|---|---|
| 1 | `fig1-intervals.png` | `reports/significance.csv` | `…8ae4eb06`, `…6170ae66` |
| 2 | `fig2-abstention.png` | `reports/abstention/{rerank,hybrid}-pr.csv` | `real-rerank-…095541-a6eb2d5e`, `real-hybrid-…092148-08d22872` |
| 3 | `fig3-error-classes.png` | `notes/error-taxonomy.md` counts | the two matrix runs above |
| 4 | `fig4-prompt-shape-cost.png` | `reports/baselines/window-cost.json` | `real-llm-20261030T113604-a5c0a3e4` |

The three `reports/figures/sweep-*.png` files are placeholder images that say
"no finished sweep run yet"; they are deliberately not used in the report.

## Deck timing

14 slides, 15:00. Speaker notes carry the clock. The demo is slide 10 at **9:00**
(A001 → A007 → A009 → U008, with the cache-replay and fixture fallbacks stated on the
slide), the taxonomy lands at 8:15 so the demo follows the diagnosis rather than the
cost argument, and the last slide leaves four numbers on screen for questions.

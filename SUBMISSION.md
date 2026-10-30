# SUBMISSION — CS5481 Topic 5, what to hand in and in what order

Read this top to bottom. Everything below is a file that already exists in this worktree
unless a step says *rebuild*. Measured facts are from `reports/submission.pdf` as it stands.

---

## 0. The four things that decide pass or desk-reject

1. **`reports/submission.pdf`** is the report with the slides appended: 23 pages.
2. **Page 9 is the contribution page** and page 10 is slide 1 — the required page sits
   immediately before the slides, outside the 6-page main-content count.
3. **Every member signs their own row on page 9.** Unsigned row = desk reject. The page is
   still a template (see §3); filling it is the only step here that no script can do.
4. **The source code zip** goes up with the PDF. Python files only, no weights, no caches,
   no keys.

---

## 1. Files to submit, and in what form

| # | Upload | File / form | Notes |
|---|---|---|---|
| 1 | Report + slides (one PDF) | `reports/submission.pdf` | the graded artifact: 9 report pages, then the 14 slides |
| 2 | Slides (if Canvas has a separate slot) | `reports/slides.pptx` (or `reports/slides.pdf`) | already appended inside `submission.pdf`; this is a convenience upload |
| 3 | Source code | `topic5-rag-code.zip` | build it with the command in §5; **`.py` files, not a notebook** — the brief allows either |
| 4 | Nothing else | — | do not upload `data/`, `runs/`, `data/cache/*.sqlite`, `.env`, or `.scratch/` |

The zip must contain, at minimum:

```
ragqa/            the pipeline (26 modules)
scripts/          the runners: run_matrix, run_sweeps, run_baselines, calibrate_judges, ...
configs/          every cell, sweep, baseline and demo configuration
golden/           v1.jsonl (the 60-item set) + SPEC.md
tests/            the offline test suite
pyproject.toml  README.md  GLOSSARY.md  .env.example
```

`notes/`, `docs/adr/` and `reports/` are evidence, not code: include them only if the zip
size allows, and never include `runs/` (6.9 MB of `chunks.jsonl` per cell) or `data/`.

---

## 2. Page-count evidence (do not re-measure, but you can)

| Check | Value | How it was measured |
|---|---|---|
| `reports/report.pdf` | 9 pages | PDF page count |
| Main content | 6 pages | `5 References` heading starts on page 6 at y = 504 of 842 pt; §1–§4 fit above it |
| Slack left on page 6 | ≈ 10.5 cm | the Discussion ends at y ≈ 490, the page ends at 816 |
| `reports/slides.pdf` | 14 pages | PDF page count |
| `reports/submission.pdf` | 23 pages = 9 + 14 | `merge_pdf.py` prints exactly this |
| Contribution page | page 9 of the report, page 9 of the submission | page 9 holds only §6; page 10 is the slide title |
| Limit | main content ≤ 6 pp; references and appendix unlimited | pages 6–7 references, pages 7–8 Appendix A |

If a rebuild changes any of these numbers, `python .scratch/topic5-rag/merge_pdf.py` prints
the report page count, the slide page count, the total, and the first line of the last page
before the slides. Read those three lines; if the middle one is not `6 Individual
Contributions`, stop and fix the pagination before uploading.

---

## 3. The contribution page — fill this in, print it, sign it

`reports/report.md` §6 renders to page 9. It is a template: `[MEMBER 1]` … `[MEMBER 8]`,
`[CONTRIBUTION]`, `[ %]`, a signature rule per row, and a `Total` row hard-coded to `100 %`.
Replace the placeholders with the real table below, delete unused rows, make the ratios sum
to exactly 100, then rebuild (§5) and confirm the page is still page 9.

| # | Member | Contribution | Ratio | Signature |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |
| 6 |  |  |  |  |
| 7 |  |  |  |  |
| 8 |  |  |  |  |
|  | **Total** |  | **100 %** |  |

Rules the brief states, in its own terms:

- the contribution statement **and the signatures of every group member** must be on a
  **separate last page of the main report**, i.e. the page right before the appended slides;
- that page does **not** count toward the 6-page main-content limit;
- a submission without that page, or without every member's signature, is **desk rejected**.

Practical order: fill the table → rebuild the PDF → print page 9 only → every member signs
their own row in ink → scan or photograph the signed page → **replace page 9 of the PDF with
the scan** (keep the same page position) → re-check with `merge_pdf.py` that it is still the
last page before the slides. Signatures are wet or scanned; a typed name is not a signature.

---

## 4. Canvas steps (5 minutes, in this order)

1. **People → Groups** — confirm the group is registered and the member list matches the
   contribution page. Registration closed 18 Oct; if the roster differs, tell the TA now.
2. **Assignments → the CS5481 project submission** — upload `reports/submission.pdf` first and
   wait for the preview to render, then confirm page 9 shows the signed contribution table.
3. Upload `topic5-rag-code.zip` as the second file (or the second slot if the assignment has
   one). Do not paste code into the comment box.
4. Comment box, one line: *"Report with slides appended (23 pp) + source code zip. Contribution
   page is p. 9, signed by all members."*
5. **Submit**, then re-open the submission and download both files back. A submission you have
   not re-opened is a submission you have not checked. Deadline **Tue 24 Nov 2026, 23:59**.

---

## 5. The one-line commands that rebuild everything

Run from the repo root. `RUNS` is the live run root; point it at the tree that has the
finished cells (the alternative root `D:\DE Project\Project\runs` holds only the early
`real-*` runs, so the matrix tables come out empty from there).

```bash
set RUNS=D:\DE Project\wt\exp\runs
```

```bash
python -m ragqa aggregate --runs "%RUNS%" --out reports
python -m ragqa sweep abstention --runs "%RUNS%" --out reports
python .scratch/topic5-rag/report_figures.py
python .scratch/topic5-rag/md_to_docx.py reports/report.md reports/report.docx
"D:/DeepSeek Harness/resources/runtime/primary-runtime/dependencies/node/bin/node.exe" "D:/DeepSeek Harness/resources/app/dsh/node_modules/@deepseek-ai/libreoffice-kit/lib/cli.js" convert --input reports/report.docx --output reports/report.pdf
python .scratch/topic5-rag/build_slides.py
"D:/DeepSeek Harness/resources/runtime/primary-runtime/dependencies/node/bin/node.exe" "D:/DeepSeek Harness/resources/app/dsh/node_modules/@deepseek-ai/libreoffice-kit/lib/cli.js" convert --input reports/slides.pptx --output reports/slides.pdf
python .scratch/topic5-rag/merge_pdf.py
```

Order matters: `aggregate` before the figures (the figures read `reports/*.csv`), the figures
before the DOCX (it embeds `assets/report/*.png`), the DOCX before the PDF, the PDFs before
the merge. If you only need the code zip:

```bash
python -c "import zipfile,pathlib; root=pathlib.Path('.'); names=[p.as_posix() for d in ('ragqa','scripts','configs','golden','tests') for p in root.joinpath(d).rglob('*.py' if d in ('ragqa','scripts','tests') else '*.yaml')]; names+=['pyproject.toml','README.md','GLOSSARY.md','.env.example','golden/v1.jsonl','golden/SPEC.md']; z=zipfile.ZipFile('topic5-rag-code.zip','w',zipfile.ZIP_DEFLATED); [z.write(n) for n in names]; z.close(); print(len(names),'files')"
```

---

## 6. Known number defects — fix these before the rebuild in §5, or fix the prose after

`notes/report-factcheck.md` is the full audit (72 claims, 8 wrong, 2 unsourced). The nine that
must not reach a grader:

| Where | Printed | Should be |
|---|---|---|
| §3.7, slide 4 | judge cost "¥0.15 per 1,000 claims" | **¥1.45** (`judge-calibration.metrics.json`: 0.04356 / 30 × 1000) |
| §3.6, slide 11 notes | "a 3× gap" | **2×** (`window-cost.json`: 9.5366 / 4.7682) |
| §4 | "five failures total" | **four** (14 − 10 retrieval) |
| §4 | "one fabricated citation out of 47 claims" | **65 in the hybrid cell** (73 in the dense cell) |
| §A.1 | citation precision "over 35 claims" | **73 claims over 35 items** |
| §2.4 table | near-miss difficulty `medium 11, hard 5` | **`medium 10, hard 6`** (and the column then sums to the printed 33) |
| §3.6 | "nineteen requests across twelve models" | **13 models** (`generator-probe.json`) |
| §4 | "A010 and A030 fail the same way in both cells" | **A030 in both; A010 is a dense-cell miss** |
| slide 2 / slide 6 | "5 baseline cells", "12 cells after the matrix" | **4 baseline cells**; drop the 12 |

And one graded gap worth more than all of them: the brief asks for **answer correctness**
(item 5) and the report prints retrieval hit rate and citation containment but no correctness
number. One sentence and one proxy number closes it — see finding F2 in
`notes/report-factcheck.md`, together with F1, the chunk-strategy comparison the six finished
`recursive_parent_child` cells now make reportable. Two more prose fixes in §3.2 that no
regeneration fixes are F6/F7 there: the `llm` row of the working-point table duplicates the
rerank curve (the bundle deletes `llm-pr.csv` for that reason), and the `0.20` threshold both
headline cells ran under has no calibration curve behind it.

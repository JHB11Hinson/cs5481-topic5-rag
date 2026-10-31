"""Bring notes/report-notes.md up to the final pass."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "notes" / "report-notes.md"

COUNTS_OLD = """| Artifact | Pages | Notes |
|---|---|---|
| `report.docx` / `report.pdf` | 10 | main content 6, references + appendix 3, contribution page 1 |
| `slides.pptx` / `slides.pdf` | 15 | 15-minute structure, demo at minute nine |
| `submission.pdf` | 25 | 10 report pages, then the 15 slides |"""

COUNTS_NEW = """| Artifact | Pages | Notes |
|---|---|---|
| `report.docx` / `report.pdf` | 10 | main content 6, references + appendix 3, contribution page 1 |
| `slides.pptx` / `slides.pdf` | 16 | 15-minute structure, demo at minute nine |
| `submission.pdf` | 26 | 10 report pages, then the 16 slides |"""

PASS_OLD = """SWEEPS_PLACEHOLDER"""

FIGURES_OLD = """| Figure | File | Drawn from |
|---|---|---|
| 1 | `fig1-abstention.png` | `reports/abstention/{dense,hybrid,rerank}-pr.csv` + `working-points.json` |
| 2 | `fig2-error-classes.png` | `notes/error-taxonomy.md` counts (14 failures, two cells) |
| 3 | `fig3-prompt-shape-cost.png` | `reports/baselines/window-cost.json` |"""

FIGURES_NEW = """| Figure | File | Drawn from |
|---|---|---|
| 1 | `fig1-abstention.png` | `reports/abstention/{dense,hybrid,rerank}-pr.csv` + `working-points.json` |
| 2 | `fig2-sweeps.png` | `reports/sweeps/{k,chunk,hops}.csv` |"""

DEFECTS_OLD = """3. `notes/error-taxonomy.md` still describes the two-cell world, since the taxonomy is a
   hand audit and has not been extended. The report cites it for exactly what it measured
   and says so in §3.5 and §3.9. `notes/prefix-ab.md` was refreshed to six usable pairs."""

DEFECTS_NEW = """3. Nothing else is stale in the bundle. `notes/error-taxonomy.{md,json}` now covers all
   eighteen cells (275 events, 40 hand-inspected), `notes/prefix-ab.md` six pairs,
   `notes/chunking-comparison.md` nine, and `notes/golden-audit.md` records the
   fourteen-item reading."""

TIMING_OLD = """15 slides, 15:00. Speaker notes carry the clock. The demo is slide 10 at **9:00**
(A001 → A007 → A009 → U008, with the cache-replay and fixture fallbacks stated on the
slide); answer correctness (slide 11) and cost (slide 12) follow it, so the added slide
does not move the demo. `build_slides.py` prints the slide count and confirms every slide
has notes."""

TIMING_NEW = """16 slides, 15:00. Speaker notes carry the clock. The demo is slide 10 at **9:00–11:15**
(A001 → A007 → A009 → U008, with the cache-replay and fixture fallbacks stated on the
slide). Everything added after the first build — sensitivity curves, answer correctness,
the reworked taxonomy — sits *after* the demo, so the demo has never moved off minute
nine. `build_slides.py` prints the slide count and confirms every slide has notes."""

PENDING_OLD = """## Still pending (not fixable from this worktree)

- **The ten sweep points** (`reports/sweeps/{k,chunk,hops}.*`): all pending, so §3.3 prints
  the declaration and no curve, and slide 13 lists them as unrun. When the CSVs land, §3.3
  gains a table per curve and Figure 4 would be the first thing to draw.
- **The contribution page** is still a template with `[MEMBER 1..8]`; it is the group's to
  fill and sign."""

PENDING_NEW = """## Still pending (not fixable from this worktree)

- **The contribution page** is still a template with `[MEMBER 1..8]`; it is the group's to
  fill and sign. That is the only unrun item left: eighteen cells, ten sweep points, five
  baseline rows, the abstention sweep, the chunking pairs, the correctness grading and the
  taxonomy are all finished and in the report."""

PASS_NEW = """A third drop landed the sweep curves and a rebuilt taxonomy, and both are larger than the
space §3.3 reserved, so this pass paid by **content, not by small print**: §3.3's ten-row
table and the prompt-shape cost figure went (the table duplicated the three paragraphs, and
the cost numbers are all in §3.7's table), and Figure 2 is now the sweep figure. §3.5 was
rebuilt on the eighteen-cell taxonomy: 275 events, 196 of them evidence that never reached
the prompt, 29 chunks dropped between `k = 10` and a window of 8, and zero
generator-over-abstention *derived* from the evidence accounting rather than assumed. §4
was rewritten around that, and §3.9 gained the `hit@10` any-of caveat (56 of 196
evidence-loss events sit on items scored as hits; recall over every gold quote is 0.73) and
the fourteen-item golden audit — containment proves a quote is real, not that it is
sufficient."""


def main():
    text = PATH.read_text(encoding="utf-8")
    for old, new in [
        (COUNTS_OLD, COUNTS_NEW),
        (FIGURES_OLD, FIGURES_NEW),
        (DEFECTS_OLD, DEFECTS_NEW),
        (TIMING_OLD, TIMING_NEW),
        (PENDING_OLD, PENDING_NEW),
    ]:
        if old not in text:
            raise SystemExit(f"missing block: {old[:60]!r}")
        text = text.replace(old, new, 1)
    marker = "`notes/prefix-ab.md` six,\nso the \"eight pairs\" and \"four pairs\" sentences are gone."
    if marker not in text:
        raise SystemExit("missing anchor for the third-pass paragraph")
    text = text.replace(marker, marker + "\n\n" + PASS_NEW, 1)
    PATH.write_text(text, encoding="utf-8")
    print("notes updated")


if __name__ == "__main__":
    main()

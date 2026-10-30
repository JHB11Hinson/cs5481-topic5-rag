"""Update PROGRESS.md for the pause: board statuses plus the resume block."""

from __future__ import annotations

import pathlib

BOARD = {
    "| 12 factorial matrix | running | 18 cells emitted, checked, projection 1080/1080; cells landing now |":
        "| 12 factorial matrix | done | 18/18 cells finished and committed under `runs/grid-*`; projection 1080/1080 |",
    "| 14 baselines + swaps | done | four baseline cells + paired McNemar |":
        "| 14 baselines + swaps | done | four baseline cells plus their reference, paired McNemar in `reports/baselines/` |",
    "| 17 report + slides | in progress | report, appendix, slides |":
        "| 17 report + slides | paused | docx/pptx/pdf built; the numbers inside predate the finished matrix |",
    "| 13 sensitivity + hops | configs done | 10 sweep cells emitted and dry-run-verified; curves need the runs |":
        "| 13 sensitivity + hops | paused | 10 sweep cells emitted and dry-run-verified; the curves need their runs |",
}

PAUSE = """## Paused here (2026-10-31, machine shut down on request)

Everything that runs unattended is finished and committed. What is left is one
number-refresh pass and two human steps.

**Done and committed:** the 18-cell matrix (`runs/grid-*`), answer correctness for all
18 cells (`reports/correctness.*`), the nine-pair chunking comparison
(`reports/chunking.*`), the v1 abstention curves with their working points, the prefix
A/B (`notes/prefix-ab.md`), the fourteen review fixes, and the independent fact-check
(`notes/report-factcheck.md`, `SUBMISSION.md`).

**Next, in order** — each step is one command:

```bash
python -m ragqa aggregate --runs runs --out reports   # the bundle, with the baselines in it
python scripts/score_correctness.py                   # cheap: every judged claim is cached
python scripts/chunk_comparison.py
```

Then the report: fold in the fifteen matrix rows, the nine numeric mismatches listed in
`notes/report-factcheck.md`, the chunking section, the correctness section, and the
sentence about the dense threshold. Re-verify the nine mismatches and three no-source
rows against the refreshed tree, and only then tick the tracker.

If there is time, the ten sensitivity cells are still unrun (plan A marks them pending):

```bash
python scripts/run_sweeps.py --runs runs --reports reports
python scripts/run_sweeps.py --curve all
```

**Two human steps, both listed in `SUBMISSION.md`:** fill and sign the contribution page
(eight rows, ratios summing to 100%) and upload to Canvas.

**Caveats to carry into the write-up.** Each is documented where it is measured, and
none is a defect to hide: the matrix cells ran with `abstain_score_threshold` 0.2 / 0.01 /
0.0 while the v1 calibration puts the working points at 0.5706 / 0.0286 / 0.4261; latency
is cache-occupancy-confounded in several cells; neither the contextual prefix nor the
recursive chunker separates from its baseline at n=40; the atomic-table hypothesis is
untestable because all eight `table_content` items are hit by both strategies; and
`verified_by` on golden v1 is `automated:corpus-anchored`, not human.

"""


def main() -> int:
    path = pathlib.Path("docs/PROGRESS.md")
    text = path.read_text(encoding="utf-8")
    for old, new in BOARD.items():
        if old in text:
            text = text.replace(old, new)
        else:
            print(f"board row not found (skipped): {old[:60]}")
    if "## Paused here" not in text:
        text = text.replace("## Measured", PAUSE + "## Measured", 1)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("progress updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

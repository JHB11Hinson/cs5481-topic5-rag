"""Final board update: every ticket done, and the numbers that closed them."""

from __future__ import annotations

import pathlib

BOARD = {
    "| 07 contextual prefixes | done | 2,203 prefixes warmed (¥0.37), 100% cache hits on re-run, 20-item audit 0% fail |":
        "| 07 contextual prefixes | done | 6 usable A/B pairs, every interval containing zero; 20-item audit 0% fail |",
    "| 12 factorial matrix | done | 18/18 cells finished and committed under `runs/grid-*`; projection 1080/1080 |":
        "| 12 factorial matrix | done | 18/18 cells; `reports/matrix.md` says 18 declared, 18 finished, 0 missing |",
    "| 13 sensitivity + hops | paused | 10 sweep cells emitted and dry-run-verified; the curves need their runs |":
        "| 13 sensitivity + hops | done | 10/10 cells; depth saturates at k=20, MRR peaks at k=5, break-even hop 2 |",
    "| 14 baselines + swaps | done | four baseline cells plus their reference, paired McNemar in `reports/baselines/` |":
        "| 14 baselines + swaps | done | 5 cells; closed book ¥0.47/1k, long context ¥4.24, MiniLM −0.25 hit@10, cheap generator ¥4.70 |",
    "| 15 aggregate + taxonomy | done | `reports/` bundle regenerated from `runs/`, nine-class taxonomy |":
        "| 15 aggregate + taxonomy | done | 275 events over 18 cells, six classes firing, one command regenerates `reports/` |",
    "| 17 report + slides | paused | docx/pptx/pdf built; the numbers inside predate the finished matrix |":
        "| 17 report + slides | done | 6 pages main, 16 slides appended, contribution page page 10, submission 26 pp |",
}

FINAL = """## Final state (2026-10-31)

Every ticket on the board is done. The build has 18 matrix cells, 10 sensitivity points and 5
baseline cells — 33 run directories of evidence plus the smoke and A/B runs — and one command
regenerates every table and figure from them:

```bash
python -m ragqa aggregate --runs runs --out reports
```

**What the project found, in the order the report makes the arguments.**

1. **The contextual prefix is a null result.** Six pairs, hit@10 −0.025 or +0.025, every paired
   interval containing zero, the sign splitting by chunk strategy rather than by retrieval mode.
   It costs ¥0.48 and 35 minutes to build and buys nothing measurable at n=40 (`ADR-0013`).
2. **Late chunking fails, and the failure is the encoder's.** 54 of 240 paired retrieval items
   lost, none gained (p < 0.000001); dense hit@10 0.275 against 0.850. The pooling swap that
   should have rescued it made it worse (0.275 → 0.025), which locates the fault in mean-pooled
   token states against a CLS-trained encoder — so the technique remains untested here, and a
   mean-pooling encoder is the first thing to run with more time (`ADR-0018`).
3. **Retrieval explains all abstention.** 64 of 64 abstentions on answerable items are the items
   whose evidence was lost first (43 document misses, 13 chunk misses, 8 window drops). There is
   no generator over-abstention to fix, and the near-misses are refused 20 of 20.
4. **The score threshold is a measurement, not a mechanism.** `LLMGenerator` never reads it, and
   no cut on any of the three scales refuses a near-miss without discarding answerable items —
   a near-miss is topically adjacent by construction, so it scores high (`ADR-0019`).
5. **`hit@10` is generous by definition.** Any-of over the gold quotes: 56 of 196 evidence-loss
   events sit on items the matrix counted as hits; recall over all gold quotes is 0.73, not 0.81.
6. **Containment proves the quote is real, not that it is sufficient.** The fourteen-item audit
   found one defective item and three quotes that are containable but not self-locating.

**The two human steps that remain** are in `SUBMISSION.md`: fill and sign the contribution page
(eight rows, ratios summing to 100%), and upload to Canvas. Nothing in the repository is waiting
on code.

**Known caveats, each documented where it is measured:** the matrix cells ran with
`abstain_score_threshold` 0.2 / 0.01 / 0.0 while the v1 calibration puts the working points at
0.5706 / 0.0286 / 0.4261; latency is cache-occupancy-confounded in several cells; `verified_by`
on golden v1 is `automated:corpus-anchored` with a fourteen-item agent audit rather than a human
review; the answer-correctness judge is a model with κ 0.857 against 30 hand labels; and every
cell ran with `judge_enabled=false`, so the taxonomy is an upper bound on answer errors.
"""


def main() -> int:
    path = pathlib.Path("docs/PROGRESS.md")
    text = path.read_text(encoding="utf-8")
    for old, new in BOARD.items():
        if old in text:
            text = text.replace(old, new)
        else:
            print(f"row not found: {old[:60]}")
    if "## Final state" in text:
        start = text.index("## Final state")
        text = text[:start]
    text = text.rstrip("\n") + "\n\n" + FINAL
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("progress finalised")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

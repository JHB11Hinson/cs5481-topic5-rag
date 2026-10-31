"""Resolve the remaining tickets in the local-markdown tracker.

Sets the `**Status:**` line, ticks the boxes that are true, and appends the evidence a
reader needs. Idempotent: a second run does not duplicate the resolution block.

    python .scratch/resolve_tickets.py --final
"""

from __future__ import annotations

import pathlib
import sys

ISSUES = pathlib.Path(".scratch/topic5-rag/issues")

FINAL = {
    "07-contextual-prefixes.md": {
        "status": "done — the mechanism works; the A/B is a null result",
        "pending": [],
        "evidence": """\
2,203 prefixes were generated for ¥0.48 (the first figure under-counted output tokens)
and a rerun reports 2,203/2,203 cache hits, 0 tokens, ¥0. The 20-item audit fails
nothing (`notes/prefix-audit.md`), and the sparse index is asserted to carry prefix
tokens by a test rather than assumed.

The A/B is the interesting part and it is **null**: six usable pairs, hit@10 −0.025 in
all three `fixed` pairs and +0.025 in `recursive/dense`, every paired bootstrap interval
containing zero, and the sign splitting by chunk strategy rather than by retrieval mode
— an interaction with one cell per corner. Citation precision moves between −0.018 and
+0.042, none significant. `notes/prefix-ab.md`.

The prefix enters the index only; the generation prompt keeps the raw chunk, so any
citation effect comes through retrieval (`ADR-0013`). What it costs is ¥0.48 and 35
minutes of generation for an index that is 12 bytes larger and measurably no better.
""",
    },
    "09-late-chunking.md": {
        "status": "done — implemented, windowed, and measured; the mechanism fails here",
        "pending": [],
        "evidence": """\
Documents are encoded in windows of 2,048 tokens with 256 of overlap, the window count
and peak VRAM are recorded per run (`context_stats.json`), and the cached span vectors
are keyed by the window geometry so a different window cannot silently reuse them
(`ADR-0015`). Queries go through the ordinary sentence encoder — the document encoder
refuses them with a sentence rather than an `AttributeError` (`ADR-0018`), which is what
six cells died of before the fix.

The A/B against plain, on the same items: late chunking versus plain on retrieval is
**b = 0, c = 54 of 240 paired items, p < 0.000001**. Dense cells fall to hit@10 0.2750
from 0.8500; hybrid and rerank are rescued to 0.8750 by the lexical branch and the
reranker, with MRR still down.

A probe settles why (`scripts/late_pooling_probe.py`, `notes/late-pooling-probe.md`):
mean-pooling the query the way the spans are pooled makes it **worse**, hit@10 0.2750 →
0.0250, 0 recovered and 10 lost. Mean-pooled token states are off-distribution for a
CLS-trained encoder, and the damage is on the document side. So document-level context
remains untested here; testing it needs a mean-pooling encoder, which is the first thing
we would run with more time.
""",
    },
    "12-factorial-matrix.md": {
        "status": "done — eighteen cells, no missing row",
        "pending": [],
        "evidence": """\
`python -m ragqa grid check configs/grid` validates all eighteen cells; the projection is
1,080 generation calls against the spec's 1,080, a 0.0% deviation, and a mismatch raises
instead of spending. The runner skips a finished cell by its resolved-config digest, and
`emit(exclude=["late_chunking"])` still produces the documented twelve-cell fallback.

All eighteen cells finished and are committed under `runs/grid-*`; `reports/matrix.md`
opens with `18 declared, 18 finished, 0 unfinished, 0 unreadable, 0 absent`. The run took
longer than one night because of three failures worth recording: a HuggingFace hub check
that hung at 0% GPU until the runner pinned the models offline, bursty TLS resets from the
gateway (now retried with jitter), and the late-chunking query encoder above.
""",
    },
    "13-sensitivity-and-agentic.md": {
        "status": "done — three curves, and the hop loop stops paying at hop one",
        "pending": [],
        "evidence": """\
Ten cells in `configs/sweeps/`, each differing from the reference cell in one parameter
and nothing else (asserted by a full key diff), depth at least k everywhere (`ADR-0011`),
and the forty answerable items selected by stratum rather than by file position — the old
`golden.limit: 40` slice gave every point zero negatives and printed its abstention
columns as `0.0` instead of `0/0`.

The agentic loop decomposes after a failed round, honours its cap, and records exactly one
of `hit_first_round` / `hit_after_rewrite` / `cap_reached` / `abstained` per item in
`hop_stats.json`. Its trigger is the v1 rerank working point (0.426134), re-derived after
the calibration moved, and a test pins that equality rather than the old divergence.

The curves and the break-even sentence are in `reports/sweeps/` and `notes/sweeps.md`.
""",
    },
    "14-baselines-and-swaps.md": {
        "status": "done — five cells, one factor each where the factor is clean",
        "pending": [],
        "evidence": """\
Four baselines plus a reference cell, all on the same forty answerable items and all
normal run directories: `runs/baseline-*`.

Closed book refuses all forty answerable questions and costs ¥0.47 per 1,000; the
whole-document long-context baseline answers all forty and is **cheaper** than the
reference cell, ¥4.24 against ¥9.10 — what it spends is the citation handle, since a
document in the prompt has no chunk to point at, and its citation precision and recall are
zero for that reason. `all-MiniLM-L6-v2` drops hit@10 from 0.90 to 0.65 at ¥7.78. The
cheap generator keeps hit@10 at 0.90 and citation precision at 0.87 for ¥4.70, a 48%
saving. `embed-minilm` moves two keys and is labelled `MULTIPLE_FACTORS(2)` rather than
pretending otherwise. Paired McNemar for each contrast is in `reports/baselines/table.md`,
computed by the same exact test the matrix table uses.
""",
    },
    "15-error-taxonomy-and-aggregate.md": {
        "status": "done — nine classes over 275 events, and one command for every table",
        "pending": [],
        "evidence": """\
`notes/error-taxonomy.md` fixes nine classes, assigns forty hand-inspected failures with a
one-line justification each, and counts **275 events per class per cell** across all
eighteen cells. Six classes fire; over-abstention, under-abstention and span-out-of-bounds
are empty, and that emptiness is a result. Three corrections the two-cell version could not
see: `hit@10` is any-of over the gold quotes, so 56 of 196 evidence-loss events were
counted as hits and all-quote recall is 0.73 rather than 0.81; `context-budget-drop` is not
empty (29 chunks lost between k=10 and `llm.context_chunks=8`, 21 items answered anyway);
and all 64 abstentions on answerable items are accounted for by evidence loss, so there is
**zero** generator over-abstention.

`python -m ragqa aggregate --runs runs --out reports` emits the matrix, the main effects,
the paired contrasts, the judge table, the cost table and the figures, with every row
naming its run id and `reports/README.md` stating that the directory is generated. A
second run is byte-identical, PNGs included.
""",
    },
    "17-report-and-slides.md": {
        "status": "done — six pages, sixteen slides appended, contribution page last",
        "pending": [],
        "evidence": """\
`reports/report.docx` runs to six pages of main content (`References` opens page 7), then
references, appendix, and the contribution page as page 10 — the last page before the
appended slides. `reports/submission.pdf` is 26 pages: 10 of report plus 16 of slides
(page counts re-checked independently of the build script). The deck is a fifteen-minute
structure with the demo at minute nine, and everything added late sits after it.

Methodology states the 18-cell design, the paired tests, the 60-item set with its strata,
and the deliberate omissions with their ADRs. Experiments carry the matrix with hit@10
bootstrap intervals, the three sensitivity curves, the abstention curve and its working
points, judge agreement, the 275-event error distribution, the four baselines and the cost
table, each naming its run id. Discussion argues from the taxonomy — 71% of classified
failures are evidence that never reached the prompt — and from the two null results and the
smaller-embedder collapse, and leads "with more time" with a mean-pooling encoder.
""",
    },
}


def resolve(path: pathlib.Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    import re

    text = re.sub(r"^\*\*Status:\*\* .*$", f"**Status:** {spec['status']}", text, count=1, flags=re.M)
    box = 0
    lines = []
    for line in text.splitlines():
        if line.startswith("- [ ]"):
            box += 1
            if box not in spec["pending"]:
                line = line.replace("- [ ]", "- [x]", 1)
        lines.append(line)
    text = "\n".join(lines) + "\n"
    if "## Resolution" not in text:
        text = text.rstrip("\n") + "\n\n## Resolution\n\n" + spec["evidence"].strip() + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"resolved {path.name}: {box - len(spec['pending'])}/{box} boxes ticked")


def main(argv=None) -> int:
    names = sys.argv[1:] or list(FINAL)
    for name in names:
        path = ISSUES / name
        if not path.exists():
            print(f"missing {path}")
            continue
        resolve(path, FINAL[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

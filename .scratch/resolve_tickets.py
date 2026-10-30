"""Resolve tickets in the local-markdown tracker.

Sets the `**Status:**` line, ticks the boxes that are done, leaves the ones that are
not, and appends the evidence a reader needs. Idempotent: running it twice does not
duplicate the resolution block.

    python .scratch/resolve_tickets.py
"""

from __future__ import annotations

import re
import pathlib

ISSUES = pathlib.Path(".scratch/topic5-rag/issues")

RESOLUTIONS = {
    "08-golden-set.md": {
        "status": "done — v1 frozen at 60 items",
        "pending": [],
        "evidence": """\
`golden/v1.jsonl` carries 60 items: `fact_lookup` 10, `param_value` 8,
`table_content` 8, `multi_hop` 8, `concept` 6, near-miss 20. The validator is green:

```
$ python -m ragqa golden validate golden/v1.jsonl --strict-quotas \\
    --corpus=data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl
golden/v1.jsonl: ok against 1268 documents
```

Quotes are extracted from the corpus by keyword (`golden/spec_v1.json` holds anchors
only, never quote text), so a retyped quote is not possible. Six items were revised
before ship and the log is in `notes/golden-v1-authoring.md`.

Two facts a reader must not paper over. `verified_by` is `automated:corpus-anchored`
on all 60 items: the quotes are provably in their documents, the *questions* were not
reviewed by a human. And v0 has a real defect that stays in v0 because a golden set is
immutable — its U005 is answerable, since the corpus does contain
`resource "vault_aws_auth_backend_role"`. v1 does not carry that item. ids are
renumbered by stratum, so v0 and v1 results are not item-comparable.
""",
    },
    "10-support-judges.md": {
        "status": "done — hosted judge gates reporting, NLI is a diagnostic",
        "pending": [],
        "evidence": """\
30 claims were labelled by hand and both judges scored against them:
Cohen's kappa **0.857** for `deepseek-v4-pro` (agreement 0.933, precision 1.000,
recall 0.900) and **0.595** for the local NLI cross-encoder (agreement 0.833).
The 0.60 bar was fixed before the numbers were seen, so NLI does not gate anything;
`notes/judge-calibration.md` states the decision and shows every disagreement.

All five NLI↔judge disagreements are `nli_only` — NLI never rejects what the judge
accepts — so its errors inflate precision rather than cost recall, and its four false
positives are exactly relation reversals and in-chunk distractors.

The layer had been **inverted end to end**: the checkpoint's label order is
`[entailment, neutral, contradiction]`, not MNLI's. The first calibration run scored
kappa −0.33 and recall 0.05. It now reads `id2label`, and a test pins the order.

Set composition is stated in the note rather than smoothed: the real-generation runs
hold 50 claims, 47 survive containment, **none is false** — real generator error shows
up as a containment failure, which never reaches a judge. The 30-item set is therefore
20 verbatim claims plus 10 controlled negatives with one documented edit each.
""",
    },
    "11-abstention-curve.md": {
        "status": "done — working points measured per retrieval mode",
        "pending": [],
        "evidence": """\
The sweep runs in a per-mode normalised space and reports the raw-scale equivalent,
because cross-encoder logits, RRF sums and cosine are three scales and one threshold
cannot serve all three. The rule was fixed before the numbers: maximise F1 of the
answer class subject to over-abstention ≤ 0.05, ties to the larger threshold.

| mode | working point | raw threshold | precision | recall | F1 | over-abstain | under-abstain |
|---|---|---|---|---|---|---|---|
| hybrid | 0.4059 | 0.030432 | 0.556 | 1.000 | 0.714 | 0.000 | 0.800 |
| rerank | 0.4471 | 0.759250 | 0.714 | 1.000 | 0.833 | 0.000 | 0.400 |

The hybrid ceiling is structural, not a tuning gap: two answerable items and five
near-misses all score exactly 0.032522 because the RRF lattice has only so many
values at k=10. No threshold separates them, and the note says so rather than moving
the working point to make the curve look better.
""",
    },
    "16-demo-ui.md": {
        "status": "done — Chainlit app, citation panel, abstention case",
        "pending": [],
        "evidence": """\
A citation marker is a `cl.Action`, not a link. Clicking it runs `open_citation`,
which rebuilds the panel from the process's own chunk store and sends a
`CitationCard` custom element carrying document title, heading path, canonical URL,
and the chunk text with the cited span wrapped in `<mark>`. The payload carries no
chunk text, so a panel cannot show stale evidence.

The five scripted questions are captured verbatim in `notes/demo-script.md`,
including A009 where the third claim is withheld as `quote_not_in_chunk`, and U008
where the system abstains and shows the best-scoring chunk (0.669) with the reason.

Chainlit 2.3.0 has no `cl.on_action` (it is `cl.action_callback`) and evaluates
element JSX in the browser, so the panel was validated by esbuild plus in-process
assertions on the element props rather than by eye. The app loads models once at
start and serves one configuration; the footer states latency and the configuration.
""",
    },
}


def resolve(path: pathlib.Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\*\*Status:\*\* .*$", f"**Status:** {spec['status']}", text, count=1, flags=re.M)

    box = 0
    lines = []
    for line in text.splitlines():
        if line.startswith("- [ ]"):
            box += 1
            if box not in spec["pending"]:
                line = line.replace("- [ ]", "- [x]", 1)
        lines.append(line)
    text = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")

    if "## Resolution" not in text:
        text = text.rstrip("\n") + "\n\n## Resolution\n\n" + spec["evidence"].strip() + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"resolved {path.name}: {box - len(spec['pending'])}/{box} boxes ticked")


def main() -> int:
    for name, spec in RESOLUTIONS.items():
        path = ISSUES / name
        if not path.exists():
            print(f"missing {path}")
            continue
        resolve(path, spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

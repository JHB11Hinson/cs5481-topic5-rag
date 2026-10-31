"""Final three cor trims to close the last lines of the six-page budget.

    python .scratch/topic5-rag/trim_lines2.py
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

EDITS = [
    (" What failed is `bge-m3` doing late chunking, not late chunking — which is why the mean-pooling encoder is the first experiment we would run.",
     " What failed is `bge-m3` doing late chunking, not late chunking."),
    (" Reading either column as an operating-point result would be reading the wrong layer.", ""),
    ("Source: `reports/matrix.md`; the full run ids, plus nDCG@10, span hit rate, abstention recall and latency, are in §A.1 and the CSV.",
     "Source: `reports/matrix.md`; full run ids, nDCG@10, span hit rate, abstention recall and latency are in §A.1."),
    ("**With more time**: set the context window to k, normalise markdown links before containment (8 of the 26 quote failures) and raise `max_tokens` for the three multi-hop items that exhaust it; re-run the late-chunking level on a mean-pooling encoder (`jina-embeddings-v2`, or an e5/gte model); enable the judge on headline cells so citation precision stops meaning containment; adopt the four golden v2 quote extensions the audit proposes and re-run the matrix on them; and have a human read the remaining twenty-six items, the one threat no amount of compute removes.",
     "**With more time**: set the context window to k, normalise markdown links before containment (8 of the 26 quote failures) and raise `max_tokens` for the three multi-hop items that exhaust it; re-run late chunking on a mean-pooling encoder (`jina-embeddings-v2`, or an e5/gte model); enable the judge on headline cells; adopt the four golden v2 quote extensions the audit proposes; and have a human read the remaining twenty-six items, the one threat no amount of compute removes."),
]


def main():
    text = REPORT.read_text(encoding="utf-8")
    for old, new in EDITS:
        if old not in text:
            raise SystemExit(f"missing: {old[:60]!r}")
        text = text.replace(old, new, 1)
    REPORT.write_text(text, encoding="utf-8")
    print(f"applied {len(EDITS)} trims")


if __name__ == "__main__":
    main()

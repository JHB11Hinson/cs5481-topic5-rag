"""Last two trims.

    python .scratch/topic5-rag/trim_lines3.py
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

EDITS = [
    ("- **The sweeps price parameters, not policies.** All three hop points share one trigger (0.426134), and the sweep cells run the 40 answerable items with no near-misses, so nothing there speaks to abstention.",
     "- **The sweeps price parameters, not policies**: one shared trigger (0.426134) and no near-misses, so nothing there speaks to abstention."),
    (" — and bounds the value of the context block under this prompt, not the model's knowledge.", "."),
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

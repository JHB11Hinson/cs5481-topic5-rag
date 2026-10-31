"""Slide-level fixes for the final pass: renumber, new timings, new threats bullets."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / ".scratch" / "topic5-rag" / "build_slides.py"

EDITS = [
    ("    # 11 — answer correctness", "    # 12 — answer correctness"),
    ('notes(slide, "11:30–12:15. This slide closes brief item 5',
     'notes(slide, "11:55–12:35. This slide closes brief item 5'),
    ("    # 12 — cost", "    # 13 — cost"),
    ('notes(slide, "12:15–13:05. Kills an argument',
     'notes(slide, "12:35–13:20. Kills an argument'),
    ("    # 13 — threats", "    # 14 — threats"),
    ('notes(slide, "13:05–13:50. Read these as commitments',
     'notes(slide, "13:20–14:05. Read these as commitments'),
    ("    # 14 — what next", "    # 15 — what next"),
    ('notes(slide, "13:50–14:35. One line per item',
     'notes(slide, "14:05–14:35. One line per item'),
    ("    # 15 — close", "    # 16 — close"),
    ('notes(slide, "14:35–15:00. Close on the two-word contract',
     'notes(slide, "14:35–15:00. Close on the two-word contract'),
    # slide 6 — the sweeps are no longer pending
    ('("Pending. ", "all 10 sweep points. Five baseline configurations ran (§cost)."),',
     '("Finished too. ", "ten sweep points across three curves, and five baseline '
     'configurations (§3.3, §3.7)."),'),
    # slide 14 — threats: replace the unrun-sweeps bullet
    ('("Ten sweep points are declared and unrun.", "The curves are pending, and the report says "\n'
     '         "so instead of drawing a line through zero points."),',
     '("hit@10 is any-of, not recall.", "It returns on the first gold quote it finds: 56 of the "\n'
     '         "196 evidence-loss events sit on items scored as hits, and recall over every gold "\n'
     '         "quote is 0.73."),\n'
     '        ("No human read the golden set.", "Fourteen items were read by the agent at the "\n'
     '         "group\'s authorisation: one defect (A038), three quotes containable but not "\n'
     '         "self-locating. Containment proves a quote is real, not that it is sufficient."),'),
]


def main():
    text = PATH.read_text(encoding="utf-8")
    for old, new in EDITS:
        if old not in text:
            raise SystemExit(f"missing: {old[:70]!r}")
        text = text.replace(old, new, 1)
    PATH.write_text(text, encoding="utf-8")
    print(f"applied {len(EDITS)} slide edits")


if __name__ == "__main__":
    main()

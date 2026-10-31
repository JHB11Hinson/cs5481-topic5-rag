"""Trim eleven lines of prose out of §2–§3 to keep the main body at six pages.

    python .scratch/topic5-rag/trim_lines.py

Each pair is (old, new); the script asserts every `old` is present, so a failed edit is
loud instead of silent.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

EDITS = [
    # §2.2 — the 5.56 GB figure is stated in §2.5 and ADR-0015; keep it once
    (" — the whole-document variant peaked at 5.56 GB of a 6.00 GB card, which is why the window exists", ""),
    # §3.2 — drop the hand-holding clause
    ("Both statements are true at once and neither is a defect: all twenty near-misses",
     "Both are true at once: all twenty near-misses"),
    # §3.3 — the exchange-rate sentence duplicates "dominated"
    (" The pre-registered expectation — precision peaking before recall — holds, and the 1,024 point buys 7.5 recall points over 512 for 47 % more money, the worst exchange on the page.",
     " The pre-registered expectation — precision peaking before recall — holds."),
    # §3.3 — one clause instead of a sentence about stop reasons
    (" The loop rewrote 3 of 40 items and recovered one; the rest stopped on the first round or at the cap, with each run's stop-reason histogram in its `hop_stats.json`.",
     " The loop rewrote 3 of 40 items and recovered one (`hop_stats.json` per run)."),
    # §3.5 — compress the quote/parse detail
    (" Of the 26 quote failures, 8 are faithful quotes whose markdown link the model flattened (`[TLS](…)` written as `TLS`), so 8 of 26 disappear if containment normalises links before comparing; the 17 parse failures are three questions at `tokens_out = 3200` against `max_tokens = 1600`, eleven of them on items that had already lost evidence.",
     " Eight of the 26 quote failures are faithful quotes whose markdown link the model flattened (`[TLS](…)` written as `TLS`), so they vanish if containment normalises links; the 17 parse failures are three questions at `tokens_out = 3200` against `max_tokens = 1600`."),
    # §3.6 — the splitter clause is implied by "paid the budget"
    (" — the splitter refused to break them and paid the budget instead", ""),
    # §3.8 — the parse-free verdict is already implied
    ("; no reply failed to parse, so every answerable item carries a verdict (`reports/correctness.json`, `notes/correctness.md`).",
     " (`reports/correctness.json`, `notes/correctness.md`)."),
    # §3.9 — fold the taxonomy caveat into the rank-interval bullet
    ("- **Rank metrics have no interval**: hit@10 is bootstrapped over items, while MRR and nDCG@10 print `missing`, because a committed run directory records which items were missed, not where the evidence ranked (§3.1).\n- **The taxonomy counts lost evidence, not wrong answers.** Every cell ran with `judge_enabled = false`, so it is an upper bound on answer errors, and its forty rows are a stratified sample sized for coverage, not for rates (§3.5).",
     "- **Rank metrics have no interval**: hit@10 is bootstrapped over items, while MRR and nDCG@10 print `missing`, because a committed run directory records which items were missed, not where the evidence ranked (§3.1). The taxonomy is the other half of that: with `judge_enabled = false` in every cell it counts lost evidence, not wrong answers, and its forty rows are sampled for coverage rather than for rates (§3.5)."),
]


def main():
    text = REPORT.read_text(encoding="utf-8")
    for old, new in EDITS:
        if old not in text:
            raise SystemExit(f"missing: {old[:70]!r}")
        text = text.replace(old, new, 1)
    REPORT.write_text(text, encoding="utf-8")
    print(f"applied {len(EDITS)} trims")


if __name__ == "__main__":
    main()

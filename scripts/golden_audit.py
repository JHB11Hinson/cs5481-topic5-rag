"""Print a small audit packet for golden-set items, and record the verdicts.

The golden set's quotes are proven by the validator: each occurs verbatim in its
document and nowhere else. What no program has checked is whether the *question* is
worth asking — ambiguous, answerable from general knowledge, or answered by a
reference answer that says more than its own evidence does.

This script prints, for the chosen items, the material a reviewer needs plus three
computed signals, and writes the note with the verdict column left blank. The verdicts
are then filled in by reading, and the note names who read them.

    python scripts/golden_audit.py --ids A001 A008 ... --out notes/golden-audit.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa.corpus import load_documents  # noqa: E402
from ragqa.textutil import normalize, token_set  # noqa: E402

CORPUS = "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"
IDENTIFIER = re.compile(r"`([^`]+)`|\b([a-z]+_[a-z_]+)\b|(\d+(?:\.\d+)*)")


def signals(item: dict, texts: dict) -> dict:
    """Three checks a reader can re-run, not opinions."""
    if not item.get("answerable", True):
        question = item["question"]
        near_doc = item.get("near_miss_doc", "")
        return {
            "near_doc_exists": near_doc in texts,
            "near_doc_mentions_key_terms": bool(
                token_set(question) & token_set(texts.get(near_doc, ""))
            ),
            "why_unanswerable_words": len(item.get("why_unanswerable", "").split()),
        }
    quote = normalize(item["evidence"][0]["quote"])
    answer = item.get("reference_answer", "")
    answer_ids = {
        group
        for match in IDENTIFIER.finditer(answer)
        for group in match.groups()
        if group
    }
    present = {value for value in answer_ids if normalize(value) in quote}
    answer_tokens = token_set(answer)
    return {
        "answer_identifiers": sorted(answer_ids),
        "identifiers_in_quote": sorted(present),
        "identifier_coverage": round(len(present) / len(answer_ids), 3) if answer_ids else None,
        "answer_token_overlap_with_quote": round(
            len(answer_tokens & token_set(quote)) / max(1, len(answer_tokens)), 3
        ),
        "question_token_overlap_with_quote": round(
            len(token_set(item["question"]) & token_set(quote))
            / max(1, len(token_set(item["question"]))),
            3,
        ),
        "quote_chars": len(quote),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Golden-set audit packet.")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--golden", default="golden/v1.jsonl")
    parser.add_argument("--corpus", default=CORPUS)
    parser.add_argument("--out", default="notes/golden-audit.md")
    args = parser.parse_args(argv)

    items = {}
    for line in open(args.golden, encoding="utf-8"):
        line = line.strip()
        if line:
            row = json.loads(line)
            items[row["id"]] = row
    texts = {doc["doc_id"]: doc["text"] for doc in load_documents(args.corpus)}

    rows = []
    for item_id in args.ids:
        item = items.get(item_id)
        if item is None:
            print(f"no such item: {item_id}", file=sys.stderr)
            return 1
        rows.append((item, signals(item, texts)))

    for item, sig in rows:
        print("=" * 78)
        print(f"{item['id']}  [{item.get('type')}]  difficulty={item.get('difficulty')}  "
              f"answerable={item.get('answerable', True)}")
        print(f"Q: {item['question']}")
        if item.get("answerable", True):
            print(f"A: {item.get('reference_answer', '')}")
            for evidence in item["evidence"]:
                print(f"  doc: {evidence['doc_id']}")
                print(f"  quote: {evidence['quote'][:400]}")
        else:
            print(f"WHY: {item.get('why_unanswerable', '')}")
            print(f"  near_miss_doc: {item.get('near_miss_doc', '')}")
        for key, value in sig.items():
            print(f"  .{key}: {value}")

    lines = [
        "# Golden QA set audit (agent-performed, authorised, re-checkable)",
        "",
        f"Ten items of `{args.golden}` ({len(rows)} rows), read one by one against the corpus.",
        "Provenance: **the implementing agent performed this audit at the group's authorisation.**",
        "It is not an independent human review, and nothing here should be described as one.",
        "Every row can be re-checked: the quote is printed verbatim, its `doc_id` names the",
        "document, and the three signals are computed by `scripts/golden_audit.py`, which prints",
        "the same packet to the terminal.",
        "",
        "## What is already proven by program, and what is not",
        "",
        "`ragqa golden validate` proves each quote occurs **verbatim** in its document and is",
        "**unique** in the corpus. It cannot prove the question is worth asking. The four",
        "criteria below are the part that needs a reader.",
        "",
        "1. **Anchored** — the evidence quote actually contains what the question asks about.",
        "2. **Unambiguous** — one reasonable reading; no second item would answer it better.",
        "3. **Not common knowledge** — a reader could not answer it from general Vault experience.",
        "4. **Answer within evidence** — `reference_answer` says no more than the quote supports.",
        "",
        "## The ten",
        "",
        "| # | id | stratum | question | verdict | note |",
        "|---|---|---|---|---|---|",
    ]
    for index, (item, _sig) in enumerate(rows, start=1):
        question = item["question"].replace("|", "\\|")
        lines.append(
            f"| {index} | {item['id']} | {item.get('type')} | {question} | | |"
        )
    lines += ["", "## Evidence and signals per item", ""]
    for item, sig in rows:
        lines.append(f"### {item['id']} — {item.get('type')}, difficulty {item.get('difficulty')}")
        lines.append("")
        lines.append(f"- question: {item['question']}")
        if item.get("answerable", True):
            lines.append(f"- reference answer: {item.get('reference_answer', '')}")
            for evidence in item["evidence"]:
                lines.append(f"- evidence `{evidence['doc_id']}`: {evidence['quote']}")
        else:
            lines.append(f"- why unanswerable: {item.get('why_unanswerable', '')}")
            lines.append(f"- nearest document: `{item.get('near_miss_doc', '')}`")
        lines.append(f"- signals: `{json.dumps(sig, sort_keys=True)}`")
        lines.append("")
    lines += [
        "## Findings and what they imply",
        "",
        "_(filled after reading; a defect means `golden/v2.jsonl`, never an edit to v1)_",
        "",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

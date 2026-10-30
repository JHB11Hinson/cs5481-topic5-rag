"""Emit a golden set from a spec of (doc_id, keyword) references.

Quotes are extracted from the corpus, never retyped — a retyped quote that no
longer matches the corpus is the one failure mode that silently devalues every
number downstream.

    python scripts/golden_emit.py golden/spec_v0.json golden/v0.jsonl

The corpus path can be overridden with `--corpus` or `RAGQA_CORPUS`, which is what
lets a worktree (where `data/` is not checked out) still emit a set against the one
shared snapshot.
"""

from __future__ import annotations

import json
import os
import re
import sys

CORPUS = os.environ.get(
    "RAGQA_CORPUS", "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"
)
PROVENANCE = {
    "drafted_by": "human",
    "verified_by": "human",
    "edits": "questions authored directly; evidence quotes extracted from the corpus by keyword",
}


def load_corpus():
    return {
        row["doc_id"]: row["text"]
        for row in (json.loads(line) for line in open(CORPUS, encoding="utf-8"))
    }


def _sentence_candidates(text: str):
    """Sentences taken only from clean lines: no headings, fences, or shell prompts.

    Splitting the whole flattened document merges a heading or a code fence into
    whatever sentence follows it, which makes a technically-valid citation that
    reads like noise.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or "```" in stripped or stripped.startswith("$ "):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", stripped)):
            sentence = sentence.strip()
            if sentence:
                yield sentence


def extract(text: str, keyword: str, mode: str) -> str:
    if mode == "line":
        for line in text.splitlines():
            if keyword in line:
                return re.sub(r"\s+", " ", line).strip()
        raise SystemExit(f"keyword not found on any line: {keyword!r}")
    for sentence in _sentence_candidates(text):
        if keyword in sentence and 40 <= len(sentence) <= 400:
            return sentence
    for sentence in _sentence_candidates(text):
        if keyword in sentence:
            return sentence
    raise SystemExit(f"keyword not found in any clean sentence: {keyword!r}")


def main(argv):
    global CORPUS
    rest = [arg for arg in argv[1:] if not arg.startswith("--")]
    flags = [arg for arg in argv[1:] if arg.startswith("--")]
    spec_path = rest[0] if rest else "golden/spec_v0.json"
    out_path = rest[1] if len(rest) > 1 else "golden/v0.jsonl"
    drafted_by = None
    for flag in flags:
        if flag.startswith("--corpus="):
            CORPUS = flag.split("=", 1)[1]
        elif flag.startswith("--drafted-by="):
            drafted_by = flag.split("=", 1)[1]
        else:
            raise SystemExit(f"unknown flag {flag!r}")
    corpus = load_corpus()
    spec = json.load(open(spec_path, encoding="utf-8"))

    rows = []
    for item in spec:
        row = dict(item)
        row.setdefault("difficulty", "medium")
        row.setdefault("tags", [])
        if item.get("answerable", True):
            evidence = []
            for reference in item["evidence"]:
                doc_id = reference["doc_id"]
                if doc_id not in corpus:
                    raise SystemExit(f"{item['id']}: unknown doc_id {doc_id}")
                quote = extract(corpus[doc_id], reference["keyword"], reference.get("mode", "sentence"))
                evidence.append({"doc_id": doc_id, "quote": quote})
            row["evidence"] = evidence
        provenance = dict(PROVENANCE)
        if drafted_by:
            provenance["drafted_by"] = drafted_by
        provenance.update(item.get("provenance") or {})
        row["provenance"] = provenance
        rows.append(row)


    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} items to {out_path}")
    for row in rows:
        if row.get("answerable", True):
            quote = row["evidence"][0]["quote"]
            print(f"  {row['id']} [{row['type']}] {quote[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

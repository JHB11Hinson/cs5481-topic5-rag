"""Probe the corpus for candidate golden-set evidence.

Prints verbatim sentences and table rows so items can be specified by
(doc_id, keyword) instead of by retyped text — retyping is how a quote stops
matching the corpus.

    python scripts/golden_probe.py defaults 8
    python scripts/golden_probe.py tables 6
    python scripts/golden_probe.py find <doc_id> <keyword>
"""

from __future__ import annotations

import json
import random
import re
import sys

CORPUS = "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"


def load():
    rows = [json.loads(line) for line in open(CORPUS, encoding="utf-8")]
    return {row["doc_id"]: row for row in rows}


def sentences(text: str):
    flat = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+", flat)


def main(argv):
    mode = argv[1] if len(argv) > 1 else "defaults"
    limit = int(argv[2]) if len(argv) > 2 else 8
    docs = load()
    random.seed(7)

    if mode == "defaults":
        found = []
        for doc_id, row in docs.items():
            if not doc_id.startswith("docs/"):
                continue
            for sentence in sentences(row["text"]):
                if (
                    "default" in sentence.lower()
                    and 80 < len(sentence) < 260
                    and "`" in sentence
                    and "](" not in sentence
                ):
                    found.append((doc_id, sentence))
                    break
        random.shuffle(found)
        for doc_id, sentence in found[:limit]:
            print(f"DEFAULT|{doc_id}|{sentence}")

    elif mode == "tables":
        found = []
        for doc_id, row in docs.items():
            lines = row["text"].splitlines()
            for index, line in enumerate(lines):
                if (
                    line.startswith("| ")
                    and index + 2 < len(lines)
                    and set(lines[index + 1].replace("|", "").replace("-", "").strip()) == set()
                    and lines[index + 2].startswith("| ")
                ):
                    found.append((doc_id, line, lines[index + 2]))
                    break
        random.shuffle(found)
        for doc_id, header, row in found[:limit]:
            print(f"TABLE|{doc_id}|HDR:{header}|ROW:{row}")

    elif mode == "find":
        doc_id, keyword = argv[2], argv[3]
        row = docs.get(doc_id)
        if row is None:
            print(f"no such document: {doc_id}")
            return 1
        for sentence in sentences(row["text"]):
            if keyword in sentence:
                print(f"{doc_id} :: {sentence}")
        return 0

    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

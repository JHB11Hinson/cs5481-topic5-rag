"""Screen all answerable items by the signal that flagged the three caveats."""

from __future__ import annotations

import json

from ragqa.corpus import load_documents
from ragqa.textutil import normalize, token_set

docs = {d["doc_id"]: d["text"] for d in load_documents("data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl")}
rows = [json.loads(line) for line in open("golden/v1.jsonl", encoding="utf-8") if line.strip()]

print(f"{'id':6s} {'type':14s} {'q-overlap':>9s} {'a-overlap':>9s}  question")
flagged = []
for row in rows:
    if not row.get("answerable", True):
        continue
    quote = " ".join(normalize(e["quote"]) for e in row["evidence"])
    q_tokens = token_set(row["question"])
    a_tokens = token_set(row.get("reference_answer", ""))
    q_overlap = len(q_tokens & token_set(quote)) / max(1, len(q_tokens))
    a_overlap = len(a_tokens & token_set(quote)) / max(1, len(a_tokens))
    if q_overlap < 0.25:
        flagged.append((row["id"], row["type"], round(q_overlap, 3), round(a_overlap, 3)))
    print(f"{row['id']:6s} {row.get('type',''):14s} {q_overlap:9.3f} {a_overlap:9.3f}  {row['question'][:70]}")

print()
print(f"items with question-overlap below 0.25: {len(flagged)} of {sum(1 for r in rows if r.get('answerable', True))}")
for row in flagged:
    print("  ", row)

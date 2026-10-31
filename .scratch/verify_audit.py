"""Verify the two judgements the audit turns on."""

from __future__ import annotations

import json
import re

from ragqa.corpus import load_documents

docs = {d["doc_id"]: d["text"] for d in load_documents("data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl")}

print("=== A015: what is 131072 in docs/concepts/tune-server-performance? ===")
text = docs["docs/concepts/tune-server-performance"]
for match in re.finditer("131072", text):
    start = max(0, match.start() - 700)
    print("--- context ---")
    print(text[start : match.end() + 120].replace("\n", " ⏎ ")[-900:])
    print()

print("=== U003: is disable_gzip anywhere in the corpus? ===")
hits = [(doc_id, tex.count("disable_gzip")) for doc_id, tex in docs.items() if "disable_gzip" in tex]
print("documents mentioning disable_gzip:", hits if hits else "none")
print("total documents:", len(docs))

print()
print("=== A022: does the quota table have a header naming the editions? ===")
text = docs["docs/concepts/resource-quotas"]
index = text.find("Rate limit quotas")
print(text[max(0, index - 400) : index + 300].replace("\n", " ⏎ "))

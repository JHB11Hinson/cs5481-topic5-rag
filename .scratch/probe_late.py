"""Why did late chunking lose 22 points of hit@10? Compare its retrieved docs to plain's."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PLAIN = Path("runs/grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910")
LATE = Path("runs/grid-recursive_parent_child-rerank-late_chunking-20261030T170813-ddf8886b")


def load(run: Path):
    rows = {}
    for line in (run / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["item_id"]] = row
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    return rows, metrics


plain, plain_m = load(PLAIN)
late, late_m = load(LATE)

print("hit@10 plain", plain_m["retrieval"]["hit_rate"], "late", late_m["retrieval"]["hit_rate"])
print("plain misses", len(plain_m["retrieval"]["misses"]), "late misses", len(late_m["retrieval"]["misses"]))
print("late-only-missed items:", sorted(set(late_m["retrieval"]["misses"]) - set(plain_m["retrieval"]["misses"]))[:12])

golden = {}
for line in Path("golden/v1.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        golden[row["id"]] = row

strata = Counter()
for item_id in late_m["retrieval"]["misses"]:
    strata[golden.get(item_id, {}).get("type", "?")] += 1
print("late misses by stratum:", dict(strata))

same_top_doc = 0
compared = 0
for item_id, row in late.items():
    if not row.get("retrieved") or item_id not in plain:
        continue
    compared += 1
    if row["retrieved"][0]["doc_id"] == plain[item_id]["retrieved"][0]["doc_id"]:
        same_top_doc += 1
print(f"top-1 doc identical between late and plain: {same_top_doc}/{compared}")

overlap = []
for item_id in sorted(late):
    a = {hit["chunk_id"] for hit in late[item_id].get("retrieved", [])}
    b = {hit["chunk_id"] for hit in plain[item_id].get("retrieved", [])}
    if a or b:
        overlap.append(len(a & b) / max(1, len(a | b)))
print(f"mean retrieved-set Jaccard: {sum(overlap) / len(overlap):.3f}")

example = next(i for i in late if late[i].get("retrieved"))
print("\nexample item", example)
print("  plain top3 docs:", [h["doc_id"] for h in plain[example]["retrieved"][:3]])
print("  late  top3 docs:", [h["doc_id"] for h in late[example]["retrieved"][:3]])
print("  late scores:", [h["score"] for h in late[example]["retrieved"][:3]])
print("  plain scores:", [h["score"] for h in plain[example]["retrieved"][:3]])

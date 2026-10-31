import json
from pathlib import Path

from ragqa import aggregate

run = Path("runs/grid-fixed-dense-plain-20261030T124637-8ae4eb06")
golden = aggregate.load_golden("golden/v1.jsonl")
loaded = aggregate.load_run_items(str(run), golden)
items = loaded["items"]

sample = next(iter(items.values()))
print("record keys:", sorted(sample.keys()))
print("retrieved[0]:", sample["retrieved"][0] if sample["retrieved"] else None)

has_text = any(
    hit.get("text") is not None
    for record in items.values()
    for hit in record["retrieved"]
)
print("any text not None:", has_text)

metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
misses = metrics["retrieval"]["misses"]
print("misses:", len(misses), misses[:3])

out = aggregate.item_outcomes(items, misses)
print("hit_source:", out["hit_source"], "rate:", out["rates"]["hit_at_10"])
print("n hits dict:", len(out["hits"]))

import json
from pathlib import Path

from ragqa import aggregate

run = Path("runs/grid-fixed-dense-plain-20261030T124637-8ae4eb06")
golden = "golden/v1.jsonl"
loaded = aggregate.load_run_items(run, golden)
print("text_available:", loaded.get("text_available"))
metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
misses = metrics["retrieval"]["misses"]
print("metrics hit_rate:", metrics["retrieval"]["hit_rate"], "| n misses:", len(misses))
outcomes = aggregate.item_outcomes(loaded["items"], misses)
answerable = outcomes["answerable"]
hits = [outcomes["hits"].get(item, None) for item in answerable]
print("answerable:", len(answerable), "hits true:", sum(1 for h in hits if h), "none:", sum(1 for h in hits if h is None))
print("hit_source:", outcomes["hit_source"], "rates.hit_at_10:", outcomes["rates"]["hit_at_10"])
print("chunks.jsonl present:", (run / "chunks.jsonl").exists())

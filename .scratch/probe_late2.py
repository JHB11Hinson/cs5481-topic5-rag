import json
from pathlib import Path

names = [
    "grid-recursive_parent_child-dense-plain",
    "grid-recursive_parent_child-dense-late_chunking",
    "grid-fixed-dense-plain",
    "grid-fixed-dense-late_chunking",
    "grid-recursive_parent_child-hybrid-plain",
    "grid-recursive_parent_child-hybrid-late_chunking",
    "grid-recursive_parent_child-rerank-plain",
    "grid-recursive_parent_child-rerank-late_chunking",
]
for name in names:
    for directory in Path("runs").glob(name + "-*"):
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        retrieval = metrics["retrieval"]
        print(
            f"{name:52s} hit@10={retrieval['hit_rate']:.4f} "
            f"mrr={retrieval['mrr']:.4f} ndcg={retrieval['ndcg_at_10']:.4f}"
        )

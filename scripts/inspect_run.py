"""Summarise one run: which items failed and why.

    python scripts/inspect_run.py runs/<run_id>
"""

from __future__ import annotations

import json
import sys


def main(argv):
    run = argv[1] if len(argv) > 1 else ""
    metrics = json.load(open(f"{run}/metrics.json", encoding="utf-8"))
    predictions = [json.loads(line) for line in open(f"{run}/predictions.jsonl", encoding="utf-8")]
    citations = [json.loads(line) for line in open(f"{run}/citations.jsonl", encoding="utf-8")]
    stats = json.load(open(f"{run}/cache_stats.json", encoding="utf-8"))
    timings = json.load(open(f"{run}/timings.json", encoding="utf-8"))

    print(f"run: {run}")
    print(
        "retrieval   hit@k={hit_rate} mrr={mrr} ndcg@10={ndcg_at_10}".format(
            **metrics["retrieval"]
        )
    )
    print(
        "citations   precision={citation_precision} recall={citation_recall} span_hit={span_hit_rate} "
        "claims={claims}".format(**metrics["citations"])
    )
    print(
        "abstention  over={over_abstain_rate} caught={abstained_unanswerable}/{unanswerable} "
        "under={under_abstain}".format(
            unanswerable=metrics["items"]["unanswerable"], **metrics["abstention"]
        )
    )
    print(
        f"llm         calls={stats.get('llm_cache_misses')} cached={stats.get('llm_cache_hits')} "
        f"tokens_in={stats.get('llm_tokens_in')} tokens_out={stats.get('llm_tokens_out')} "
        f"p50={timings.get('p50_ms')} ms"
    )

    print("\nper item:")
    for row in predictions:
        supported = sum(1 for c in citations if c["item_id"] == row["item_id"] and c["supported"])
        total = sum(1 for c in citations if c["item_id"] == row["item_id"])
        flag = "abstain" if row["abstained"] else f"claims={total} ok={supported}"
        print(
            f"  {row['item_id']:<6} answerable={str(row['answerable']):<5} {flag:<20} "
            f"{row['abstain_reason'][:40]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

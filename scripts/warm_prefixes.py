"""Warm the contextual-prefix cache for a whole corpus (ticket 07).

Prefix generation is the one expensive part of the contextualization factor: one
cheap-model call per child chunk (2,203 of them on this corpus). Warming it once,
before any cell of the matrix runs, means every later cell reports 100% cache hits
and the A/B against the plain level is a comparison rather than two samples.

    python scripts/warm_prefixes.py --config configs/ctx-prefix.yaml
    python scripts/warm_prefixes.py --config configs/ctx-prefix.yaml   # 100% hits

Writes `data/prefix_stats.json` with the cost, token counts, and prefix length
distribution the report quotes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import chunk as chunk_mod  # noqa: E402
from ragqa import config as config_mod  # noqa: E402
from ragqa import corpus  # noqa: E402
from ragqa import context as context_mod  # noqa: E402
from ragqa import run as run_mod  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Warm the prefix cache.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="data/prefix_stats.json")
    parser.add_argument("--limit", type=int, default=0, help="stop after N chunks (smoke)")
    args = parser.parse_args(argv)

    cfg = config_mod.load(args.config)
    docs = corpus.load_documents(cfg["corpus.source"])
    docs_by_id = {doc["doc_id"]: doc for doc in docs}
    chunks = chunk_mod.build(
        docs,
        cfg["chunk.strategy"],
        int(cfg["chunk.size"]),
        int(cfg["chunk.overlap"]),
        int(cfg["chunk.parent_size"]),
    )
    children = [c for c in chunks if c["kind"] == "child"]
    if args.limit:
        children = children[: args.limit]
    print(f"documents: {len(docs)}  child chunks: {len(children)}")

    prefixer = run_mod._make_prefixer(cfg)
    stats = prefixer.generate(children, docs_by_id, neighbours=int(cfg["context.prefix_neighbours"]))
    summary = prefixer.summary()

    price_in = float(cfg["llm.price_in_usd_per_mtok"])
    cost_usd = summary["tokens_in"] / 1e6 * price_in + summary["tokens_out"] / 1e6 * price_in
    summary["cost_usd"] = round(cost_usd, 6)
    summary["cost_cny"] = round(cost_usd * 6.67, 6)
    summary["hit_rate"] = round(
        summary["cache_hits"] / max(1, summary["cache_hits"] + summary["cache_misses"]), 4
    )
    summary["corpus_snapshot"] = cfg["corpus.snapshot_id"]
    summary["chunk_set"] = chunk_mod.chunk_set_id(
        cfg["corpus.snapshot_id"],
        cfg["chunk.strategy"],
        int(cfg["chunk.size"]),
        int(cfg["chunk.overlap"]),
        int(cfg["chunk.parent_size"]),
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        "hits={h} misses={m} tokens_in={i} tokens_out={o} p50={p} chars cost=¥{c}".format(
            h=summary["cache_hits"],
            m=summary["cache_misses"],
            i=summary["tokens_in"],
            o=summary["tokens_out"],
            p=summary["prefix_p50_chars"],
            c=summary["cost_cny"],
        )
    )
    print(f"-> {args.out}")
    prefixer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

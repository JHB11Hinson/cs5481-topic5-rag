"""Inspect a chunk set: sizes, outliers, and the documents they came from.

    python scripts/inspect_chunks.py data/chunks/<set_id>/chunks.jsonl [top]
"""

from __future__ import annotations

import json
import statistics
import sys


def main(argv):
    path = argv[1] if len(argv) > 1 else ""
    top = int(argv[2]) if len(argv) > 2 else 5
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    children = [row for row in rows if row["kind"] == "child"]
    parents = [row for row in rows if row["kind"] == "parent"]
    children.sort(key=lambda row: -row["token_count"])
    print(f"{path}\n  children={len(children)} parents={len(parents)}")
    print(
        "  mean={:.1f} median={} p95={} max={}".format(
            statistics.mean(row["token_count"] for row in children),
            statistics.median(row["token_count"] for row in children),
            sorted(row["token_count"] for row in children)[int(0.95 * (len(children) - 1))],
            children[0]["token_count"],
        )
    )
    for row in children[:top]:
        print(f"  {row['token_count']:>6}  {row['doc_id']}  {row['text'][:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Move the matrix's run directories from the experiment worktree into the repo.

The matrix runs in a separate git worktree so that editing code cannot change the
code a running cell executes. Its output is the evidence the report cites, so it has
to end up committed here, with the two excluded artifacts replaced by checksums.

    python scripts/collect_matrix_runs.py --from "D:\DE Project\wt\exp\runs"
    python scripts/collect_matrix_runs.py --from <path> --dry-run

Refuses to copy a run directory that has no `metrics.json`: a directory with a
`config.json` and no metrics is not a run (`ADR-0003`), and copying one would put a
lie in `runs/` that the aggregate step then has to defend against.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.fetch_artifacts import backfill  # noqa: E402


def collect(source: str, target: str, dry_run: bool = False) -> int:
    if not os.path.isdir(source):
        print(f"no such source: {source}", file=sys.stderr)
        return 1
    os.makedirs(target, exist_ok=True)
    copied, skipped, unreadable = [], [], []
    for name in sorted(os.listdir(source)):
        run_dir = os.path.join(source, name)
        if not os.path.isdir(run_dir):
            continue
        if name.endswith(".partial"):
            # The cell that is executing right now writes here; it is not evidence yet.
            continue
        destination = os.path.join(target, name)
        if os.path.exists(destination):
            skipped.append(name)
            continue
        if not os.path.exists(os.path.join(run_dir, "metrics.json")):
            unreadable.append(name)
            continue
        if dry_run:
            copied.append(name)
            continue
        shutil.copytree(
            run_dir,
            destination,
            ignore=shutil.ignore_patterns("chunks.jsonl", "corpus_snapshot.json", "*.partial"),
        )
        backfill(destination)
        copied.append(name)

    for name in copied:
        print(f"{'would copy' if dry_run else 'copied'} {name}")
    for name in skipped:
        print(f"already here: {name}")
    for name in unreadable:
        print(f"NOT a run (no metrics.json), left behind: {name}", file=sys.stderr)
    print(f"\n{len(copied)} copied, {len(skipped)} already present, {len(unreadable)} unreadable")
    return 0 if not unreadable else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect matrix run directories.")
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("--to", dest="target", default="runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return collect(args.source, args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

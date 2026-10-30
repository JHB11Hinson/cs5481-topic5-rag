"""Scratch: dump the failure candidates the taxonomy is hand-classified from.

Not part of the report bundle and not a deliverable. Re-run it when more cells of
the matrix finish, then rewrite `notes/error-taxonomy.md` against the dump.

    python scripts/inspect_failures.py "D:\\DE Project\\wt\\exp\\runs" failures.json
"""

from __future__ import annotations

import json
import sys

from ragqa import aggregate


def main(argv: list) -> int:
    runs_root = argv[1] if len(argv) > 1 else "runs"
    out = argv[2] if len(argv) > 2 else "failures.json"
    candidates = aggregate.failure_candidates(runs_root)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(candidates, handle, indent=2, sort_keys=True)
    by_category = {}
    for candidate in candidates:
        by_category[candidate["category"]] = by_category.get(candidate["category"], 0) + 1
    print("%d candidate(s) from %s" % (len(candidates), runs_root))
    for category in sorted(by_category):
        print("  %-20s %d" % (category, by_category[category]))
    cells = {}
    for candidate in candidates:
        cells.setdefault(candidate["run_id"], 0)
        cells[candidate["run_id"]] += 1
    print("by run:")
    for run_id in sorted(cells):
        print("  %-52s %d" % (run_id, cells[run_id]))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

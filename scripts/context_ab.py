"""The contextual-prefix A/B, written as `notes/prefix-ab.md`.

    python scripts/context_ab.py --runs runs --out notes/prefix-ab.md

GPU-free and read-only: it pairs every finished `contextual_prefix` cell with its
`plain` twin and reads the two run directories. A twin that has not finished is
reported as pending, never as a zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import context_ab  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Contextual-prefix A/B on the golden set")
    parser.add_argument("--configs", default=context_ab.DEFAULT_CONFIGS)
    parser.add_argument("--runs", default=context_ab.DEFAULT_RUNS)
    parser.add_argument("--golden", default=context_ab.DEFAULT_GOLDEN)
    parser.add_argument("--out", default=os.path.join("notes", "prefix-ab.md"))
    parser.add_argument(
        "--json",
        default="",
        help="also print the machine-readable report to this path ('-' for stdout)",
    )
    args = parser.parse_args(argv)

    data = context_ab.main(
        configs_dir=args.configs,
        runs_root=args.runs,
        golden_path=args.golden,
        out=args.out,
    )
    if args.json:
        text = json.dumps(data, indent=2, sort_keys=True)
        if args.json == "-":
            print(text)
        else:
            with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
            print("wrote %s" % args.json)
    return 0 if data["summary"]["refused"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

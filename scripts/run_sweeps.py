"""One command for the ticket-13 sensitivity sweeps.

    python scripts/run_sweeps.py --emit            # write configs/sweeps/*.yaml
    python scripts/run_sweeps.py --check           # validate them, spend nothing
    python scripts/run_sweeps.py --dry-run         # project calls/cost, spend nothing
    python scripts/run_sweeps.py                   # execute the pending points
    python scripts/run_sweeps.py --curve all       # reports/sweeps/{k,chunk,hops}.{csv,md,png}
    python scripts/run_sweeps.py --curve hops      # just the hop curve

The three curves live in `ragqa/sweeps.py`, so every behaviour here is the same code
the `python -m ragqa sweep ...` sub-command calls. Nothing is executed unless no
`--emit` / `--check` / `--dry-run` / `--curve` action was asked for, and `--dry-run`
never imports the pipeline.
"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import sweeps  # noqa: E402  (after the sys.path fix for `python scripts/...`)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_sweeps.py",
        description="Emit, check, run and plot the sensitivity sweeps (ticket 13).",
    )
    parser.add_argument("--configs", default=sweeps.DEFAULT_CONFIG_DIR,
                        help="directory holding the emitted sweep configurations")
    parser.add_argument("--runs", default=sweeps.DEFAULT_RUNS_ROOT,
                        help="run root the finished points are read from and written to")
    parser.add_argument("--reports", default=sweeps.DEFAULT_REPORTS_DIR,
                        help="directory the curve artifacts are written into")
    parser.add_argument("--emit", action="store_true",
                        help="write (or refresh) the configuration for every point")
    parser.add_argument("--check", action="store_true",
                        help="load every configuration and verify the declaration")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the projection and execute nothing")
    parser.add_argument("--force", action="store_true",
                        help="ignore finished run directories and re-run every point")
    parser.add_argument("--curve", default="",
                        help="write the curve artifacts for k, chunk, hops or all")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    status = 0
    acted = False

    if args.emit:
        written = sweeps.emit(args.configs)
        print("emitted %d sweep configuration(s) into %s" % (len(written), args.configs))
        for path in written:
            print("  %s" % os.path.basename(path))
        acted = True

    if args.check or args.emit:
        # Emitting is a claim about the declaration; checking it is the gate before
        # any money is spent.
        status = sweeps.check([args.configs])
        acted = True
        if status != 0:
            return status

    if args.curve:
        acted = True
        if args.curve not in ("all", "k", "chunk", "hops"):
            print(
                "unknown curve %r; choose k, chunk, hops or all" % args.curve,
                file=sys.stderr,
            )
            return 2
        status = max(
            status,
            sweeps.curves(args.runs, args.reports)
            if args.curve == "all"
            else sweeps.curve(args.curve, runs_root=args.runs, out=args.reports),
        )

    if args.dry_run:
        acted = True
        status = max(status, sweeps.run([args.configs], dry_run=True, out_root=args.runs))

    if not acted:
        status = sweeps.run(
            [args.configs], dry_run=False, force=args.force, out_root=args.runs
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())

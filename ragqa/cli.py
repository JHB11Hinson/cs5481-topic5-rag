"""One command surface for everything that is not a single run.

`python -m ragqa.run` executes one configuration and stays the only way to
produce a run directory. Everything a reader or an experimenter wants to do
*around* runs lives here:

    python -m ragqa golden validate golden/v1.jsonl
    python -m ragqa golden emit golden/spec_v1.json golden/v1.jsonl
    python -m ragqa grid emit --out configs/grid
    python -m ragqa grid check configs/grid
    python -m ragqa grid run --out configs/grid
    python -m ragqa verify --run runs/<run_id>
    python -m ragqa sweep abstention --runs runs
    python -m ragqa aggregate --runs runs --out reports
    python -m ragqa serve --config configs/grid/cell-....yaml

Sub-commands are imported lazily so that a missing optional dependency (chainlit,
matplotlib) only breaks the command that needs it, never the test suite.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

DEFAULT_CORPUS = "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"


def _golden_validate(args: argparse.Namespace) -> int:
    from .corpus import load_documents
    from .golden import validate

    docs = load_documents(args.corpus)
    problems = validate(args.path, docs, strict_quotas=args.strict_quotas)
    if problems:
        for problem in problems:
            print(f"PROBLEM {problem}", file=sys.stderr)
        print(f"{len(problems)} problem(s) in {args.path}", file=sys.stderr)
        return 1
    print(f"{args.path}: ok against {len(docs)} documents")
    return 0


def _golden_emit(args: argparse.Namespace) -> int:
    import subprocess

    return subprocess.call(
        [sys.executable, "scripts/golden_emit.py", args.spec, args.out],
        cwd=".",
    )


def _grid(args: argparse.Namespace) -> int:
    from . import grid

    if args.action == "emit":
        paths = grid.emit(out_dir=args.out, inventory=not args.no_inventory)
        print(f"emitted {len(paths)} configurations into {args.out}")
        for path in paths:
            print(f"  {path.name}")
        return 0
    if args.action == "check":
        return grid.check(args.paths or [args.out])
    if args.action == "run":
        return grid.run(args.paths or [args.out], dry_run=args.dry_run, force=args.force)
    raise SystemExit(f"unknown grid action {args.action!r}")


def _verify(args: argparse.Namespace) -> int:
    from . import judges

    return judges.rerun_verification(args.run, write=not args.dry_run)


def _sweep(args: argparse.Namespace) -> int:
    from . import abstain

    if args.what == "abstention":
        return abstain.sweep_command(
            runs_root=args.runs, out=args.out, modes=args.modes
        )
    raise SystemExit(f"unknown sweep target {args.what!r}")


def _aggregate(args: argparse.Namespace) -> int:
    from . import aggregate

    return aggregate.command(runs_root=args.runs, out=args.out)


def _serve(args: argparse.Namespace) -> int:
    from . import demo

    return demo.main(["--config", args.config])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragqa", description="Grounded documentation QA.")
    sub = parser.add_subparsers(dest="command", required=True)

    golden = sub.add_parser("golden", help="golden QA set tooling")
    golden_sub = golden.add_subparsers(dest="action", required=True)
    validate = golden_sub.add_parser("validate", help="check a golden set before it is used")
    validate.add_argument("path")
    validate.add_argument("--corpus", default=DEFAULT_CORPUS)
    validate.add_argument("--strict-quotas", action="store_true")
    validate.set_defaults(func=_golden_validate)
    emit = golden_sub.add_parser("emit", help="extract quotes from a spec into a golden set")
    emit.add_argument("spec")
    emit.add_argument("out")
    emit.set_defaults(func=_golden_emit)

    grid = sub.add_parser("grid", help="the experiment matrix")
    grid_sub = grid.add_subparsers(dest="action", required=True)
    for action in ("emit", "check", "run"):
        node = grid_sub.add_parser(action)
        node.add_argument("paths", nargs="*", help="config files or directories")
        node.add_argument("--out", default="configs/grid")
        node.add_argument("--no-inventory", action="store_true")
        node.add_argument("--dry-run", action="store_true")
        node.add_argument("--force", action="store_true")
        node.set_defaults(func=_grid)

    verify = sub.add_parser("verify", help="re-run citation verification on a finished run")
    verify.add_argument("--run", required=True)
    verify.add_argument("--dry-run", action="store_true")
    verify.set_defaults(func=_verify)

    sweep = sub.add_parser("sweep", help="post-hoc sweeps over finished runs")
    sweep.add_argument("what", choices=["abstention"])
    sweep.add_argument("--runs", default="runs")
    sweep.add_argument("--out", default="reports")
    sweep.add_argument("--modes", nargs="*", default=None)
    sweep.set_defaults(func=_sweep)

    aggregate = sub.add_parser("aggregate", help="runs/ -> report tables and figures")
    aggregate.add_argument("--runs", default="runs")
    aggregate.add_argument("--out", default="reports")
    aggregate.set_defaults(func=_aggregate)

    serve = sub.add_parser("serve", help="single-screen demo over one configuration")
    serve.add_argument("--config", required=True)
    serve.set_defaults(func=_serve)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

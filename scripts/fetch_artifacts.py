"""Rebuild the large artifacts a run excluded from git, and prove they match.

`runs/<run_id>/` holds the evidence for every number in the report. Two of its
files are too big to commit and completely re-derivable — the chunk set and the
corpus snapshot digest — so they are excluded and their sha256 is committed in
`artifacts.json` instead. This script rebuilds them from the run's own
`config.json` and fails loudly when the rebuilt bytes differ from the recorded
checksum, which is the only way a "just regenerate it" claim means anything.

A run directory that holds an excluded artifact but no manifest has no committed
checksum, so its bytes cannot be verified at all: that is a failure, not a no-op.
Only a directory with neither an artifact nor a manifest is skipped.

    python scripts/fetch_artifacts.py --run runs/<run_id>
    python scripts/fetch_artifacts.py --runs runs          # every run directory
    python scripts/fetch_artifacts.py --run runs/<id> --verify-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import chunk as chunk_mod  # noqa: E402
from ragqa import config as config_mod  # noqa: E402
from ragqa import corpus as corpus_mod  # noqa: E402

#: The artifacts a run excludes from git (ADR-0003, spec item 5). Their presence
#: without a manifest is the state this script exists to refuse.
EXCLUDED_ARTIFACTS = ("chunks.jsonl", "corpus_snapshot.json")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def missing_manifest_problem(run_dir: str) -> str:
    """Why a run directory with excluded artifacts and no manifest is a failure."""
    present = [
        name
        for name in EXCLUDED_ARTIFACTS
        if os.path.exists(os.path.join(run_dir, name))
    ]
    if not present:
        return ""
    return (
        f"{run_dir}: {', '.join(present)} present but no artifacts.json, so there is no "
        "committed checksum to verify against -- run with --backfill to record one"
    )


def rebuild(run_dir: str, verify_only: bool = False) -> int:
    manifest_path = os.path.join(run_dir, "artifacts.json")
    if not os.path.exists(manifest_path):
        problem = missing_manifest_problem(run_dir)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        print(f"{run_dir}: no artifacts.json and no excluded artifacts, nothing to verify")
        return 0
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    checksums = manifest.get("checksums") or {}
    config = config_mod.load(os.path.join(run_dir, "config.json"))

    problems = 0
    for name, record in checksums.items():
        target = os.path.join(run_dir, name)
        if verify_only:
            if not os.path.exists(target):
                print(f"{run_dir}: {name} absent (verify-only, skipped)")
                continue
        elif not os.path.exists(target):
            if name == "chunks.jsonl":
                if str(config["context.mode"]) == "contextual_prefix":
                    # The chunk file of a prefix cell is written after the prefixer
                    # mutated each child in place, so it carries generated text. The
                    # prefix cache is the only copy of that text; a rebuild from
                    # config.json would produce the plain chunk set and "fail" a
                    # checksum that is in fact correct. Say so instead of pretending.
                    print(
                        f"{run_dir}: {name} is absent and cannot be rebuilt: a "
                        "contextual_prefix run's chunk file carries the generated "
                        "prefixes, which only the prefix cache holds. Re-run the cell "
                        "(the cache makes it a hit) or restore the file.",
                        file=sys.stderr,
                    )
                    problems += 1
                    continue
                docs = corpus_mod.load_documents(config["corpus.source"])
                rows = chunk_mod.build(
                    docs,
                    config["chunk.strategy"],
                    int(config["chunk.size"]),
                    int(config["chunk.overlap"]),
                    int(config["chunk.parent_size"]),
                )
                with open(target, "w", encoding="utf-8", newline="\n") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                print(f"{run_dir}: rebuilt {name} ({len(rows)} rows)")
            elif name == "corpus_snapshot.json":
                docs = corpus_mod.load_documents(config["corpus.source"])
                snapshot = corpus_mod.snapshot_identity(docs, config["corpus.snapshot_id"])
                with open(target, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(snapshot, handle, indent=2, sort_keys=True, ensure_ascii=False)
                    handle.write("\n")
                print(f"{run_dir}: rebuilt {name} ({snapshot['documents']} documents)")
            else:
                print(f"{run_dir}: do not know how to rebuild {name}", file=sys.stderr)
                problems += 1
                continue

        actual = sha256_of(target)
        expected = record.get("sha256", "")
        if expected and actual != expected:
            print(
                f"{run_dir}: {name} does NOT match the committed checksum "
                f"(expected {expected[:12]}, got {actual[:12]})",
                file=sys.stderr,
            )
            problems += 1
        else:
            print(f"{run_dir}: {name} ok ({record.get('bytes', 0)} bytes)")
    return 1 if problems else 0


def backfill(run_dir: str) -> int:
    """Write `artifacts.json` for a run produced before checksums were recorded."""
    manifest_path = os.path.join(run_dir, "artifacts.json")
    if os.path.exists(manifest_path):
        return 0
    checksums = {}
    for name in EXCLUDED_ARTIFACTS:
        target = os.path.join(run_dir, name)
        if os.path.exists(target):
            checksums[name] = {
                "sha256": sha256_of(target),
                "bytes": os.path.getsize(target),
            }
    if not checksums:
        return 0
    contextual = False
    try:
        with open(os.path.join(run_dir, "config.json"), encoding="utf-8") as handle:
            tree = json.load(handle)
        contextual = str((tree.get("context") or {}).get("mode") or "") == "contextual_prefix"
    except (OSError, ValueError):
        contextual = False
    payload = {
        "excluded_from_git": sorted(checksums),
        "checksums": checksums,
        "rebuild": "python scripts/fetch_artifacts.py --run <this directory>",
        "backfilled": "checksums computed from files present at backfill time",
    }
    if contextual:
        # Recorded so a reader knows why a rebuild cannot reproduce the bytes.
        payload["not_rebuildable"] = (
            "chunks.jsonl carries the generated contextual prefixes, which only the "
            "prefix cache holds; a rebuild from config.json produces the plain chunk "
            "set. The checksum is of the file as written, not of a rebuild."
        )
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"{run_dir}: backfilled artifacts.json")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild excluded run artifacts.")
    parser.add_argument("--run", default=None, help="one run directory")
    parser.add_argument("--runs", default=None, help="a runs root: every directory")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--backfill", action="store_true",
                        help="write artifacts.json for runs that predate it")
    args = parser.parse_args(argv)

    if not args.run and not args.runs:
        parser.error("pass --run <dir> or --runs <root>")
    targets = []
    if args.run:
        targets.append(args.run)
    if args.runs:
        for entry in sorted(os.listdir(args.runs)):
            path = os.path.join(args.runs, entry)
            if os.path.isdir(path):
                targets.append(path)

    failures = 0
    for target in targets:
        if args.backfill:
            failures += backfill(target)
        else:
            failures += rebuild(target, verify_only=args.verify_only)
    print(f"{len(targets)} run(s) checked, {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The `runs/<run_id>/` contract (ADR-0003).

One run directory is the unit of evidence. Everything a reader would need to
re-execute and re-check a number lives here, and nothing that varies between two
identical runs is written into `metrics.json` — determinism is an acceptance
criterion, so wall-clock numbers go to `timings.json` instead.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

RUN_FILES = (
    "config.json",
    "git_sha.txt",
    "corpus_snapshot.json",
    "models.json",
    "metrics.json",
    "predictions.jsonl",
    "citations.jsonl",
    "timings.json",
    "errors.jsonl",
    "cache_stats.json",
    "chunks.jsonl",
    "chunk_stats.json",
)


def git_state(cwd: str = ".") -> Dict[str, Any]:
    def run(args):
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=False
        )

    try:
        head = run(["git", "rev-parse", "--short", "HEAD"])
    except FileNotFoundError:
        return {"sha": "unversioned", "dirty": None, "note": "git executable not found"}
    if head.returncode != 0:
        return {
            "sha": "unversioned",
            "dirty": None,
            "note": "not a git repository",
        }
    status = run(["git", "status", "--porcelain"])
    return {
        "sha": head.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
        "note": "",
    }


class RunContract:
    def __init__(self, out_root: str, run_id: str):
        self.run_id = run_id
        self.path = Path(out_root) / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        target = self.path / name
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        return target

    def write_jsonl(self, name: str, rows: Iterable[Dict[str, Any]]) -> Path:
        target = self.path / name
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
                handle.write("\n")
        return target

    def write_text(self, name: str, text: str) -> Path:
        target = self.path / name
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        return target

    def missing(self) -> list:
        return [name for name in RUN_FILES if not (self.path / name).exists()]


def relative(path: str) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return path

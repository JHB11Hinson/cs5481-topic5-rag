"""The artifact manifest: a run that excludes bytes must publish their checksum.

Seam under test: `scripts/fetch_artifacts.py`'s `rebuild` and `backfill`, which are
what `--runs runs` and `--runs runs --backfill` run per directory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import fetch_artifacts  # noqa: E402


def _run_dir(root: Path, name: str, artifacts=("chunks.jsonl",)) -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "config.json").write_text(
        json.dumps(
            {
                "corpus": {"source": "fixtures/smoke/docs.jsonl", "snapshot_id": "fixture"},
                "chunk": {"strategy": "fixed", "size": 32, "overlap": 8, "parent_size": 64},
            }
        ),
        encoding="utf-8",
    )
    for artifact in artifacts:
        (path / artifact).write_text('{"row": 1}\n', encoding="utf-8")
    return path


def test_a_run_with_excluded_artifacts_and_no_manifest_is_a_failure():
    """This used to print "nothing to rebuild" and exit 0."""
    root = Path(tempfile.mkdtemp(prefix="artifacts-"))
    run = _run_dir(root, "run-a", artifacts=("chunks.jsonl", "corpus_snapshot.json"))

    assert fetch_artifacts.rebuild(str(run)) == 1
    assert fetch_artifacts.rebuild(str(run), verify_only=True) == 1
    assert not (run / "artifacts.json").exists()


def test_a_run_with_no_excluded_artifacts_is_skipped_not_failed():
    root = Path(tempfile.mkdtemp(prefix="artifacts-"))
    run = _run_dir(root, "run-b", artifacts=())

    assert fetch_artifacts.rebuild(str(run)) == 0
    assert fetch_artifacts.rebuild(str(run), verify_only=True) == 0


def test_backfill_records_the_checksums_it_finds_and_then_verifies():
    root = Path(tempfile.mkdtemp(prefix="artifacts-"))
    run = _run_dir(root, "run-c", artifacts=("chunks.jsonl",))

    assert fetch_artifacts.backfill(str(run)) == 0
    manifest = json.loads((run / "artifacts.json").read_text(encoding="utf-8"))
    assert manifest["excluded_from_git"] == ["chunks.jsonl"], manifest
    assert manifest["checksums"]["chunks.jsonl"]["sha256"] == fetch_artifacts.sha256_of(
        str(run / "chunks.jsonl")
    ), manifest

    # With a manifest in place the directory verifies instead of failing.
    assert fetch_artifacts.rebuild(str(run), verify_only=True) == 0

    # A byte that moved since the manifest was written is still caught.
    (run / "chunks.jsonl").write_text('{"row": 2}\n', encoding="utf-8")
    assert fetch_artifacts.rebuild(str(run), verify_only=True) == 1


def test_the_cli_exit_code_follows_the_per_directory_failures():
    root = Path(tempfile.mkdtemp(prefix="artifacts-"))
    _run_dir(root, "run-d", artifacts=("corpus_snapshot.json",))
    assert fetch_artifacts.main(["--runs", str(root)]) == 1
    assert fetch_artifacts.main(["--runs", str(root), "--backfill"]) == 0
    assert fetch_artifacts.main(["--runs", str(root)]) == 0


def test_a_contextual_prefix_chunk_file_is_reported_as_unrebuildable():
    """Its chunk file carries generated prefixes the config cannot reproduce."""
    root = Path(tempfile.mkdtemp(prefix="artifacts-"))
    run = _run_dir(root, "run-e", artifacts=("chunks.jsonl",))
    (run / "config.json").write_text(
        json.dumps(
            {
                "corpus": {"source": "fixtures/smoke/docs.jsonl", "snapshot_id": "fixture"},
                "chunk": {"strategy": "fixed", "size": 32, "overlap": 8, "parent_size": 64},
                "context": {"mode": "contextual_prefix", "prefix_model": "cheap"},
            }
        ),
        encoding="utf-8",
    )
    assert fetch_artifacts.backfill(str(run)) == 0
    manifest = json.loads((run / "artifacts.json").read_text(encoding="utf-8"))
    assert "not_rebuildable" in manifest, manifest
    assert "prefix cache" in manifest["not_rebuildable"], manifest

    (run / "chunks.jsonl").unlink()
    assert fetch_artifacts.rebuild(str(run)) == 1
    # Nothing was invented in its place.
    assert not (run / "chunks.jsonl").exists()

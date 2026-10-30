from __future__ import annotations

import os
import tempfile

from ragqa import config as config_mod

BASE = """
corpus:
  source: fixtures/smoke/docs.jsonl
  snapshot_id: fixture-smoke-v1
golden:
  items_path: fixtures/smoke/golden.jsonl
"""


def _write(text: str) -> str:
    handle, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    return path


def test_defaults_are_filled_in():
    cfg = config_mod.load(_write(BASE))
    assert cfg["retrieval.mode"] == "dense"
    assert cfg["chunk.size"] == 512
    assert cfg["context.mode"] == "plain"


def test_unknown_key_is_rejected_by_name():
    path = _write(BASE + "\nretrieval:\n  mode: dense\n  kk: 3\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "retrieval.kk" in str(exc)
    else:
        raise AssertionError("unknown key was silently accepted")


def test_missing_required_key_is_rejected():
    path = _write("corpus:\n  source: x\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "missing required" in str(exc).lower()
    else:
        raise AssertionError("missing required key was accepted")


def test_overlap_must_be_smaller_than_size():
    path = _write(BASE + "\nchunk:\n  size: 16\n  overlap: 16\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("overlap >= size was accepted")


def test_invalid_enum_value_is_rejected():
    path = _write(BASE + "\nretrieval:\n  mode: magic\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("invalid enum value was accepted")

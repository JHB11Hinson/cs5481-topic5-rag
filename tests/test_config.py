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


def test_no_configuration_file_hardcodes_a_model_endpoint():
    """AGENTS.md: endpoints and keys come from the environment, never from a file.

    Every YAML under `configs/` is loaded through the closed schema, so a config
    that stopped being valid also fails here rather than at run time.
    """
    offenders = []
    for directory, _subdirectories, names in os.walk("configs"):
        for name in sorted(names):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(directory, name)
            cfg = config_mod.load(path)
            if str(cfg["llm.base_url"] or "").strip():
                offenders.append(path)
    assert not offenders, "hardcoded llm.base_url in " + ", ".join(offenders)


def test_llm_client_uses_the_environment_endpoint_when_the_config_is_empty():
    """The empty `llm.base_url` default is what lets the environment supply it."""
    from ragqa.llm import LLMClient

    cache = os.path.join(tempfile.mkdtemp(prefix="ragqa-llm-"), "llm.sqlite")
    previous = {name: os.environ.get(name) for name in ("LLM_BASE_URL", "LLM_API_KEY")}
    os.environ["LLM_BASE_URL"] = "https://gateway.invalid/v1/"
    os.environ["LLM_API_KEY"] = "placeholder-key"
    try:
        client = LLMClient(base_url="", cache_path=cache)
        assert client.base_url == "https://gateway.invalid/v1"
        client.close()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_the_gap_policy_defaults_to_strict_abstention():
    cfg = config_mod.load(_write(BASE))
    assert cfg["generate.ungrounded_answer"] == "abstain"
    assert cfg["generate.ungrounded_max_tokens"] == 400


def test_the_gap_policy_needs_a_model_behind_it():
    path = _write(BASE + "\ngenerate:\n  ungrounded_answer: assist\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "ungrounded_answer=assist" in str(exc)
    else:
        raise AssertionError("assist was accepted with the stub generator")


def test_an_unknown_gap_policy_is_rejected():
    path = _write(BASE + "\ngenerate:\n  ungrounded_answer: sometimes\n")
    try:
        config_mod.load(path)
    except config_mod.ConfigError as exc:
        assert "sometimes" in str(exc)
    else:
        raise AssertionError("unknown gap policy was accepted")

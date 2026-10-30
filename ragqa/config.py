"""Configuration loading with a closed schema.

A typo in a YAML file must fail loudly, so unknown keys are rejected rather than
ignored (ticket 01). Defaults are declared here once; a config file overrides
them and nothing else.
"""

from __future__ import annotations

from typing import Any, Dict, List

import yaml

DEFAULTS: Dict[str, Any] = {
    "run.name": "run",
    "run.out_root": "runs",
    "corpus.source": None,
    "corpus.snapshot_id": None,
    "chunk.strategy": "fixed",
    "chunk.size": 512,
    "chunk.overlap": 64,
    "chunk.parent_size": 1024,
    "embed.provider": "stub",
    "embed.model_id": "stub-hashing",
    "embed.dim": 256,
    "embed.device": "auto",
    "embed.batch_size": 16,
    "embed.max_seq_length": 8192,
    "embed.cache_path": "data/cache/embeddings.sqlite",
    "embed.late_max_seq_length": 8192,
    "index.backend": "memory",
    "index.path": "data/index",
    "retrieval.mode": "dense",
    "retrieval.k": 5,
    "retrieval.reranker": "BAAI/bge-reranker-v2-m3",
    "retrieval.rerank_top": 12,
    "retrieval.rerank_max_length": 512,
    "retrieval.rrf_k": 60,
    "context.mode": "plain",
    "generate.provider": "stub",
    "generate.model_id": "stub-generator",
    "generate.abstain_score_threshold": 0.2,
    "generate.min_claim_overlap": 0.12,
    "generate.max_claims": 2,
    "golden.items_path": None,
    "golden.limit": None,
    "llm.base_url": "",
    "llm.cache_path": "data/cache/llm.sqlite",
    "llm.model_generate": "",
    "llm.model_judge": "",
    "llm.timeout": 120,
    "llm.temperature": 0.0,
    "llm.max_tokens": 900,
    "llm.context_chunks": 8,
    "llm.session_header": "x-opencode-session",
    "llm.session_id": "",
    "llm.price_in_usd_per_mtok": 0.0,
    "llm.price_out_usd_per_mtok": 0.0,
}

REQUIRED: List[str] = ["corpus.source", "corpus.snapshot_id"]

VALID_VALUES = {
    "chunk.strategy": {"fixed", "recursive_parent_child"},
    "embed.provider": {"stub", "bge-m3"},
    "index.backend": {"memory", "qdrant"},
    "retrieval.mode": {"dense", "hybrid", "rerank"},
    "context.mode": {"plain", "contextual_prefix", "late_chunking"},
    "generate.provider": {"stub", "llm"},
}


class ConfigError(ValueError):
    pass


def _flatten(tree: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def _nest(flat: Dict[str, Any]) -> Dict[str, Any]:
    tree: Dict[str, Any] = {}
    for path, value in flat.items():
        node = tree
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return tree


class Config:
    def __init__(self, values: Dict[str, Any]):
        self._values = values

    def get(self, path: str) -> Any:
        return self._values[path]

    def __getitem__(self, path: str) -> Any:
        return self._values[path]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._values)

    def nested(self) -> Dict[str, Any]:
        return _nest(self._values)

    def __repr__(self) -> str:
        return f"Config({len(self._values)} keys)"


def load(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    provided = _flatten(raw)
    unknown = sorted(set(provided) - set(DEFAULTS))
    if unknown:
        raise ConfigError(
            f"{path}: unknown config key(s): {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(DEFAULTS))}"
        )

    missing = [key for key in REQUIRED if provided.get(key) is None]
    if missing:
        raise ConfigError(f"{path}: missing required key(s): {', '.join(missing)}")

    values = dict(DEFAULTS)
    values.update({k: v for k, v in provided.items() if v is not None})

    for key, allowed in VALID_VALUES.items():
        if values[key] not in allowed:
            raise ConfigError(
                f"{path}: {key}={values[key]!r} is not one of {sorted(allowed)}"
            )

    k = int(values["retrieval.k"])
    if k < 1:
        raise ConfigError(f"{path}: retrieval.k must be >= 1, got {k}")
    if int(values["chunk.overlap"]) >= int(values["chunk.size"]):
        raise ConfigError(
            f"{path}: chunk.overlap ({values['chunk.overlap']}) must be smaller "
            f"than chunk.size ({values['chunk.size']})"
        )
    return Config(values)

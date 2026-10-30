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
    # Bounded agentic loop (ticket 13): hops = 1 is plain single-shot retrieval,
    # so the main matrix is unaffected by the mechanism existing.
    "retrieval.hops": 1,
    "retrieval.hop_rewrite_model": "",
    # Runtime trigger for another retrieval round; None falls back to the
    # generator's abstain threshold. It is a score on the retrieval mode's own
    # scale, which is why it is per-configuration and not a constant.
    "retrieval.trigger_threshold": None,
    "context.mode": "plain",
    # Contextual prefixes (ticket 07): one cheap-model call per chunk, cached by
    # (model, prompt hash) so a rerun is free and byte-identical.
    "context.prefix_model": "",
    "context.prefix_prompt_version": "v1",
    "context.prefix_max_tokens": 200,
    "context.prefix_concurrency": 4,
    "context.prefix_neighbours": 1,
    # A prefix is mechanical work: leaving the thinking channel on burns 10-20x the
    # output tokens and can return empty content inside a small budget.
    "context.prefix_reasoning_effort": "none",
    "context.prefix_cache_path": "data/cache/prefixes.sqlite",
    # Late chunking (ticket 09): documents are encoded whole, but the window is
    # capped well below the model's 8,192 so the 6 GB card keeps headroom.
    "context.window_tokens": 2048,
    "context.window_overlap": 256,
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
    # Empty means the provider default (thinking on). Mechanical calls pass "none".
    "llm.reasoning_effort": "",
    "llm.context_chunks": 8,
    "llm.session_header": "x-opencode-session",
    "llm.session_id": "",
    "llm.price_in_usd_per_mtok": 0.0,
    "llm.price_out_usd_per_mtok": 0.0,
    "llm.price_judge_in_usd_per_mtok": 0.0,
    "llm.price_judge_out_usd_per_mtok": 0.0,
    # Support judges (ticket 10). The NLI layer is local and free; the model layer
    # costs money, so it is opt-in per configuration and its cost is recorded.
    "judge.enabled": False,
    "judge.nli_model": "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
    "judge.nli_threshold": 0.5,
    "judge.llm_model": "",
    "judge.llm_max_chars": 2000,
    # Baselines (ticket 14).
    "baseline.closed_book": False,
    "baseline.long_context": False,
    "baseline.long_context_max_chars": 12000,
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
    if int(values["context.window_overlap"]) >= int(values["context.window_tokens"]):
        raise ConfigError(
            f"{path}: context.window_overlap ({values['context.window_overlap']}) must be "
            f"smaller than context.window_tokens ({values['context.window_tokens']})"
        )
    if int(values["retrieval.hops"]) < 1:
        raise ConfigError(f"{path}: retrieval.hops must be >= 1, got {values['retrieval.hops']}")
    if values["baseline.closed_book"] and values["baseline.long_context"]:
        raise ConfigError(
            f"{path}: baseline.closed_book and baseline.long_context are different "
            "questions about retrieval; enable one at a time"
        )
    if values["context.mode"] == "contextual_prefix" and not values["context.prefix_model"]:
        raise ConfigError(
            f"{path}: context.mode=contextual_prefix needs context.prefix_model "
            "(the cheap model whose prefixes get cached)"
        )
    return Config(values)

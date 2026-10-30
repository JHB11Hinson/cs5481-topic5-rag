"""Cross-run comparison for the ablation cells (ticket 14).

A baseline is only evidence if it is a run directory like any other (ADR-0003),
so nothing here executes a model: it reads `runs/<run_id>/` and produces the table
that makes a comparison arguable.

Two things are computed rather than asserted:

* **Ceteris paribus.** ADR-0003 says an ablation differs in exactly one factor.
  `substantive_diff` lists the config keys that moved and `differing_factors`
  groups them, so "exactly one factor" is checked per table instead of trusted.
  Identity keys (`run.name`, `run.out_root`, golden path and limit) are ignored:
  they name a cell and its measuring instrument, they do not change behaviour.
* **Paired significance.** Every comparison is paired by `item_id`, because both
  configurations answer the identical golden set. McNemar's test on the
  discordant pairs is the paired test for binary outcomes; with few discordant
  pairs (which is what 40 items produce) the chi-square approximation is not
  trustworthy, so the exact conditional binomial is used up to
  `EXACT_MAX_DISCORDANT` and printed with its own pair counts.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Keys that name a cell rather than describe its behaviour. A baseline must not
# be credited with "differing in one factor" because it was called something else.
IDENTITY_KEYS = frozenset(
    {"run.name", "run.out_root", "golden.items_path", "golden.limit"}
)

# Which config keys move together as one experimental factor. A factor can span
# several keys when the keys are one decision: a generator swap has to carry the
# generator's price or its cost column would describe the old model, and the
# MiniLM cell is defined as dense-only because the cross-encoder would repair the
# recall the cell exists to measure.
FACTOR_GROUPS: Dict[str, frozenset] = {
    "baseline-policy": frozenset(
        {
            "baseline.closed_book",
            "baseline.long_context",
            "baseline.long_context_max_chars",
        }
    ),
    "embedder": frozenset(
        {
            "embed.provider",
            "embed.model_id",
            "embed.dim",
            "embed.device",
            "embed.batch_size",
            "embed.max_seq_length",
            "embed.cache_path",
            "retrieval.mode",
        }
    ),
    "generator-model": frozenset(
        {
            "generate.provider",
            "llm.model_generate",
            "llm.price_in_usd_per_mtok",
            "llm.price_out_usd_per_mtok",
            "llm.price_judge_in_usd_per_mtok",
            "llm.price_judge_out_usd_per_mtok",
        }
    ),
    "generation-policy": frozenset(
        {
            "generate.abstain_score_threshold",
            "generate.min_claim_overlap",
            "generate.max_claims",
            "llm.max_tokens",
            "llm.temperature",
            "llm.reasoning_effort",
            "llm.context_chunks",
        }
    ),
    "retrieval-depth": frozenset(
        {
            "retrieval.k",
            "retrieval.reranker",
            "retrieval.rerank_top",
            "retrieval.rerank_max_length",
            "retrieval.rrf_k",
            "retrieval.hops",
            "retrieval.hop_rewrite_model",
            "retrieval.trigger_threshold",
        }
    ),
    "contextualization": frozenset(
        {
            "context.mode",
            "context.window_tokens",
            "context.window_overlap",
            "context.prefix_model",
            "context.prefix_prompt_version",
            "context.prefix_max_tokens",
            "context.prefix_neighbours",
        }
    ),
    "chunking": frozenset(
        {"chunk.strategy", "chunk.size", "chunk.overlap", "chunk.parent_size"}
    ),
    "judging": frozenset(
        {
            "judge.enabled",
            "judge.nli_model",
            "judge.nli_threshold",
            "judge.llm_model",
            "judge.llm_max_chars",
        }
    ),
    "corpus": frozenset(
        {"corpus.source", "corpus.snapshot_id", "index.backend", "index.path"}
    ),
}

# Exact conditional McNemar up to this many discordant pairs. Above it the
# continuity-corrected chi-square is used, which is the conventional cut.
EXACT_MAX_DISCORDANT = 25

METRICS_WITH_SIGNIFICANCE = ("citation_support", "retrieval_hit")

# Table name for the paired metric -> the per-item outcome field it is read from.
OUTCOME_FIELD = {"citation_support": "citation_support", "retrieval_hit": "hit"}


# --------------------------------------------------------------------------- #
# configuration diffs
# --------------------------------------------------------------------------- #


def flatten(tree: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


def _values(cfg) -> Dict[str, Any]:
    if hasattr(cfg, "as_dict"):
        return dict(cfg.as_dict())
    return flatten(cfg)


def substantive_diff(reference, other) -> Dict[str, Any]:
    """Config keys whose values differ, identity keys excluded."""
    left, right = _values(reference), _values(other)
    diff: Dict[str, Any] = {}
    for key in sorted(set(left) | set(right)):
        if key in IDENTITY_KEYS:
            continue
        if left.get(key) != right.get(key):
            diff[key] = {"reference": left.get(key), "other": right.get(key)}
    return diff


def differing_factors(diff: Iterable[str]) -> List[str]:
    """Group differing keys into declared factors; unknown keys are their own."""
    factors = set()
    for key in diff:
        for name, keys in FACTOR_GROUPS.items():
            if key in keys:
                factors.add(name)
                break
        else:
            factors.add(key)
    return sorted(factors)


# --------------------------------------------------------------------------- #
# McNemar
# --------------------------------------------------------------------------- #


def mcnemar_counts(treatment_only: int, baseline_only: int) -> Dict[str, Any]:
    """Paired significance for two binary outcomes on the same items.

    `treatment_only` counts items the treatment got right and the baseline did
    not; `baseline_only` counts the reverse. Items both agree on carry no
    information about a difference and are excluded from the test.

    The test itself lives in `aggregate.mcnemar_exact` so the baseline table and
    the matrix's significance table cannot disagree about a p-value. It is the
    exact conditional binomial at every sample size: 60 paired items is small
    enough that a chi-square approximation buys nothing and can only add error.
    """
    from .aggregate import mcnemar_exact  # local: keeps the import graph acyclic

    treatment_only = int(treatment_only)
    baseline_only = int(baseline_only)
    if treatment_only < 0 or baseline_only < 0:
        raise ValueError("discordant pair counts cannot be negative")

    exact = mcnemar_exact(treatment_only, baseline_only)
    return {
        "discordant": exact["pairs"],
        "treatment_only": treatment_only,
        "baseline_only": baseline_only,
        "statistic": exact["statistic"],
        "p_value": exact["p_value"],
        "method": "exact_binomial",
    }


def mcnemar_outcomes(pairs: Sequence[Tuple[bool, bool]]) -> Dict[str, Any]:
    """Pair outcomes as `(baseline, treatment)` and test them."""
    pairs = [(bool(base), bool(treatment)) for base, treatment in pairs]
    treatment_only = sum(1 for base, treatment in pairs if treatment and not base)
    baseline_only = sum(1 for base, treatment in pairs if base and not treatment)
    result = mcnemar_counts(treatment_only, baseline_only)
    result["pairs"] = len(pairs)
    return result


# --------------------------------------------------------------------------- #
# run directories
# --------------------------------------------------------------------------- #


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_run(path: str) -> Dict[str, Any]:
    """Everything the table needs from one immutable run directory."""
    path = str(path).rstrip("/\\")
    if not os.path.isdir(path):
        raise FileNotFoundError(f"not a run directory: {path}")
    metrics_path = os.path.join(path, "metrics.json")
    if not os.path.exists(metrics_path):
        raise ValueError(
            f"{path}: no metrics.json, so the run was never measured (ADR-0003)"
        )

    config = _read_json(os.path.join(path, "config.json"))
    metrics = _read_json(metrics_path)
    timings_path = os.path.join(path, "timings.json")
    timings = _read_json(timings_path) if os.path.exists(timings_path) else {}

    predictions = {}
    for row in _read_jsonl(os.path.join(path, "predictions.jsonl")):
        predictions[row["item_id"]] = row
    citations: Dict[str, List[Dict[str, Any]]] = {}
    for row in _read_jsonl(os.path.join(path, "citations.jsonl")):
        citations.setdefault(row["item_id"], []).append(row)

    return {
        "run_id": os.path.basename(path),
        "path": path,
        "config": flatten(config),
        "metrics": metrics,
        "timings": timings,
        "predictions": predictions,
        "citations": citations,
    }


def item_outcomes(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Per-item binary outcomes, computed from the run's own artifacts."""
    misses = set(run["metrics"].get("retrieval", {}).get("misses") or [])
    outcomes: Dict[str, Dict[str, Any]] = {}
    for item_id, prediction in run["predictions"].items():
        citations = run["citations"].get(item_id, [])
        claims = prediction.get("claims") or []

        def any_layer(name: str) -> Tuple[bool, int]:
            judged = [c[name] for c in citations if c.get(name) is not None]
            return any(bool(value) for value in judged), len(judged)

        nli, nli_judged = any_layer("nli_supported")
        judged, judged_count = any_layer("judge_supported")
        outcomes[item_id] = {
            "answerable": bool(prediction.get("answerable", True)),
            "abstained": bool(prediction.get("abstained")),
            "claims": len(claims),
            "citation_support": any(bool(c.get("supported")) for c in citations),
            "containment_support": any(
                bool(c.get("containment_ok", c.get("supported"))) for c in citations
            ),
            "nli_support": nli if nli_judged else None,
            "judge_support": judged if judged_count else None,
            "judge_judged": judged_count,
            "hit": item_id not in misses,
        }
    return outcomes


def _tokens(run: Dict[str, Any]) -> Tuple[int, int]:
    system = run["metrics"].get("system", {}) or {}
    generation = (system.get("cost_components") or {}).get("generation") or {}
    if "tokens_in" in generation or "tokens_out" in generation:
        return int(generation.get("tokens_in") or 0), int(generation.get("tokens_out") or 0)
    tokens_in = sum(int(p.get("tokens_in") or 0) for p in run["predictions"].values())
    tokens_out = sum(int(p.get("tokens_out") or 0) for p in run["predictions"].values())
    return tokens_in, tokens_out


def _cny_per_1k(run: Dict[str, Any]) -> float:
    system = run["metrics"].get("system", {}) or {}
    if "cost_per_1k_questions_cny" in system:
        return round(float(system["cost_per_1k_questions_cny"]), 4)
    total = len(run["predictions"]) or 1
    return round(float(system.get("cost_usd") or 0.0) * 6.67 * (1000.0 / total), 4)


def _row(run: Dict[str, Any], reference: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = run["metrics"]
    grounding = metrics.get("grounding") or {}
    outcomes = item_outcomes(run)
    answerable = {item for item, entry in outcomes.items() if entry["answerable"]}
    tokens_in, tokens_out = _tokens(run)

    diff = substantive_diff(reference["config"], run["config"]) if reference else {}
    factors = differing_factors(diff) if reference else []

    return {
        "run_id": run["run_id"],
        "run_dir": run["path"],
        "closed_book": bool(run["config"].get("baseline.closed_book")),
        "long_context": bool(run["config"].get("baseline.long_context")),
        "embedding_model": (metrics.get("system") or {}).get("embedding_model", ""),
        "generator_model": (metrics.get("system") or {}).get("generator_model", ""),
        "items": len(outcomes),
        "answerable_items": len(answerable),
        "k": int((metrics.get("retrieval") or {}).get("k") or 0),
        "hit_at_k": float((metrics.get("retrieval") or {}).get("hit_rate") or 0.0),
        "mrr": float((metrics.get("retrieval") or {}).get("mrr") or 0.0),
        "ndcg_at_10": float((metrics.get("retrieval") or {}).get("ndcg_at_10") or 0.0),
        "citation_precision": float((metrics.get("citations") or {}).get("citation_precision") or 0.0),
        "citation_recall": float((metrics.get("citations") or {}).get("citation_recall") or 0.0),
        # A layer that judged nothing has no precision: 0.0 would read as "every
        # claim it saw was unsupported", which is a different statement.
        "nli_precision": float(grounding.get("nli_precision") or 0.0)
        if int(grounding.get("nli_judged") or 0)
        else None,
        "nli_judged": int(grounding.get("nli_judged") or 0),
        "judge_precision": float(grounding.get("judge_precision") or 0.0)
        if int(grounding.get("judge_judged") or 0)
        else None,
        "judge_judged": int(grounding.get("judge_judged") or 0),
        "citation_support_items": sum(
            1
            for item, entry in outcomes.items()
            if entry["answerable"] and entry["citation_support"]
        ),
        "over_abstain_rate": float(
            (metrics.get("abstention") or {}).get("over_abstain_rate") or 0.0
        ),
        "abstention_recall_on_negatives": float(
            (metrics.get("abstention") or {}).get("abstention_recall_on_negatives") or 0.0
        ),
        "latency_p50_ms": float(run["timings"].get("p50_ms") or 0.0),
        "latency_p95_ms": float(run["timings"].get("p95_ms") or 0.0),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "cny_per_1k_questions": _cny_per_1k(run),
        "answers_with_no_citation": sum(
            1
            for entry in outcomes.values()
            if not entry["abstained"] and entry["claims"] == 0
        ),
        "differing_keys_vs_reference": sorted(diff),
        "differing_factors_vs_reference": factors,
        "ceteris_paribus": reference is None or len(factors) <= 1,
        "golden_items_path": run["config"].get("golden.items_path", ""),
    }


# --------------------------------------------------------------------------- #
# the table
# --------------------------------------------------------------------------- #


def _paired(run, reference, metric: str) -> Tuple[List[str], List[Tuple[bool, bool]]]:
    field = OUTCOME_FIELD[metric]
    left = item_outcomes(reference)
    right = item_outcomes(run)
    shared = [
        item
        for item in sorted(set(left) & set(right))
        if left[item]["answerable"] and right[item]["answerable"]
    ]
    return shared, [(bool(left[item][field]), bool(right[item][field])) for item in shared]


def compare(runs: Sequence[str], reference: Optional[str] = None) -> Dict[str, Any]:
    """Read two or more run directories and pair them against a reference cell."""
    loaded = [load_run(path) for path in runs]
    if len(loaded) < 2:
        raise ValueError(
            "compare needs two or more run directories: one baseline on its own "
            "cannot be compared with anything"
        )

    if reference is None:
        base = loaded[0]
    else:
        wanted = str(reference).rstrip("/\\")
        matches = [
            run
            for run in loaded
            if run["path"] == wanted or run["run_id"] == os.path.basename(wanted)
        ]
        if not matches:
            raise ValueError(f"reference run {reference!r} is not among the runs given")
        base = matches[0]

    rows = [_row(run, base) for run in loaded]

    comparisons: List[Dict[str, Any]] = []
    for run in loaded:
        if run is base:
            continue
        for metric in METRICS_WITH_SIGNIFICANCE:
            shared, pairs = _paired(run, base, metric)
            entry = {
                "metric": metric,
                "base_run_id": base["run_id"],
                "run_id": run["run_id"],
                "paired_items": len(shared),
                "golden_mismatch": len(shared) != len(run["predictions"]),
            }
            entry.update(mcnemar_outcomes(pairs))
            comparisons.append(entry)

    return {
        "reference_run_id": base["run_id"],
        "reference_run_dir": base["path"],
        "configurations": rows,
        "comparisons": comparisons,
    }


COLUMNS = [
    ("run", "run_id"),
    ("hit@k", "hit_at_k"),
    ("cit P", "citation_precision"),
    ("cit R", "citation_recall"),
    ("NLI P", "nli_precision"),
    ("judge P", "judge_precision"),
    ("over-abst", "over_abstain_rate"),
    ("p50 ms", "latency_p50_ms"),
    ("p95 ms", "latency_p95_ms"),
    ("tok in", "tokens_in"),
    ("tok out", "tokens_out"),
    ("CNY/1k", "cny_per_1k_questions"),
    ("no-cite", "answers_with_no_citation"),
    ("factors vs ref", "differing_factors_vs_reference"),
]


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        if not value:
            return "-"
        if len(value) > 2:
            return f"{len(value)} factors"
        return ", ".join(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.0f}" if abs(value) >= 1000 else f"{value:.4g}"
    return str(value)


def render_markdown(table: Dict[str, Any], title: str = "Baseline comparison") -> str:
    rows = table["configurations"]
    lines = [f"# {title}", ""]
    present = [row for row in rows if row["run_id"]]
    lines.append(f"Reference cell: `{table['reference_run_id']}`")
    lines.append("")
    lines.append("| " + " | ".join(name for name, _ in COLUMNS) + " |")
    lines.append("|" + "|".join("---" for _ in COLUMNS) + "|")
    for row in present:
        cells = [_cell(row.get(key, "")) for _, key in COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append(
        "`hit@k` is retrieval hit rate on answerable items; `cit P` / `cit R` are the "
        "containment layer's citation precision and item-level recall; `NLI P` and "
        "`judge P` are only filled when that layer judged claims; `over-abst` is the "
        "rate at which answerable items were refused; `no-cite` counts answers that "
        "name no citation at all."
    )
    lines.append("")

    lines.append("## Paired significance")
    lines.append("")
    lines.append(
        "Both configurations answer the identical golden items, so outcomes are paired "
        "by `item_id`. McNemar's test uses only the discordant pairs; the exact "
        "conditional binomial is used at or below "
        f"{EXACT_MAX_DISCORDANT} discordant pairs, the continuity-corrected "
        "chi-square above it."
    )
    lines.append("")
    lines.append(
        "| metric | run vs reference | paired items | baseline only | treatment only "
        "| statistic | p | method |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for entry in table["comparisons"]:
        statistic = "-" if entry.get("statistic") is None else f"{entry['statistic']:.4g}"
        lines.append(
            "| {metric} | {run} | {paired} | {b} | {t} | {stat} | {p:.4g} | {method} |".format(
                metric=entry["metric"],
                run=entry["run_id"],
                paired=entry["paired_items"],
                b=entry["baseline_only"],
                t=entry["treatment_only"],
                stat=statistic,
                p=entry["p_value"],
                method=entry["method"],
            )
        )
    lines.append("")
    lines.append(
        "`baseline only` counts items the reference got right and the other cell got "
        "wrong; `treatment only` is the reverse. A claim of improvement needs the "
        "treatment-only side to dominate *and* p below 0.05."
    )
    lines.append("")

    lines.append("## Ceteris paribus")
    lines.append("")
    for row in present:
        keys = row["differing_keys_vs_reference"]
        if row["run_id"] == table["reference_run_id"]:
            lines.append(f"- `{row['run_id']}`: reference cell.")
            continue
        verdict = "one factor" if row["ceteris_paribus"] else "MORE THAN ONE FACTOR"
        lines.append(
            f"- `{row['run_id']}`: {verdict}"
            + (f" ({', '.join(row['differing_factors_vs_reference'])})" if keys else "")
            + (f"; keys: {', '.join(f'`{key}`' for key in keys)}" if keys else "")
            + "."
        )
    lines.append("")
    return "\n".join(lines)


def report(
    runs: Sequence[str],
    out_dir: str,
    reference: Optional[str] = None,
    stem: str = "table",
    title: str = "Baseline comparison",
) -> Dict[str, str]:
    """Write `<out_dir>/<stem>.{md,json}` and return both paths."""
    table = compare(runs, reference=reference)
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{stem}.json")
    markdown_path = os.path.join(out_dir, f"{stem}.md")
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(table, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    with open(markdown_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown(table, title=title))
    return {"json": json_path, "markdown": markdown_path}


# --------------------------------------------------------------------------- #
# resume
# --------------------------------------------------------------------------- #


def completed_run(root: str, cfg) -> Optional[str]:
    """The newest finished run directory that belongs to this configuration.

    "Belongs to" means every config key the two have in common agrees. Run ids
    carry a UTC timestamp, so sorting the candidates makes "newest" well defined.
    """
    if not os.path.isdir(root):
        return None
    wanted = _values(cfg)
    name = str(wanted.get("run.name", ""))
    found = None
    for entry in sorted(os.listdir(root)):
        if not entry.startswith(f"{name}-"):
            continue
        path = os.path.join(root, entry)
        if not os.path.isfile(os.path.join(path, "metrics.json")):
            continue
        try:
            existing = flatten(_read_json(os.path.join(path, "config.json")))
        except (OSError, ValueError):
            continue
        shared = set(existing) & set(wanted)
        if shared and all(existing[key] == wanted[key] for key in shared):
            found = path
    return found

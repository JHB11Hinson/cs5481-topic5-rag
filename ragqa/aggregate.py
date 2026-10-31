"""`python -m ragqa aggregate --runs <root> --out reports`: run directories in, the
report bundle out.

The rule this module exists to enforce: every number in the bundle comes from a
run directory that the table names, and a cell that produced no run is printed as
`missing` rather than dropped. A partially written run directory (no
`metrics.json`) is not a run, so it cannot enter a mean.

Three things are deliberate and are worth knowing before reading the output:

*   **Cells are matched by resolved configuration, not by timestamp.** A cell's
    digest is recomputed from its YAML with `grid.config_digest`, exactly the rule
    `grid.plan()` uses to resume. The digest stored in `configs/grid/grid.json` is
    written at emit time and goes stale the moment a default in `config.py`
    changes, so it is reported as drift and never used as a join key.
*   **Headline metrics are recomputed from the item artifacts** (`predictions.jsonl`,
    `citations.jsonl`, `chunks.jsonl`) and compared against `metrics.json`. A
    disagreement is printed, not hidden, because a table that silently trusts one
    of the two cannot be checked against the other.
*   **Intervals resample items, not claims.** A question is the unit that was
    sampled from the world; its claims are not independent of it. The seed and the
    number of resamples are printed in every table that carries an interval.

Nothing here writes into a run directory: the input is read-only and the whole
output lives under `--out`.
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import zlib
from fractions import Fraction
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import evaluate as evaluate_mod
from . import grid
from . import judges

# ---- the protocol ----------------------------------------------------------

#: Fixed so a reader can reproduce an interval exactly; printed in the tables.
BOOTSTRAP_SEED = 20261030
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_CONFIDENCE = 0.95

#: The headline metrics, in report order: (key in `values`, column label).
HEADLINE: Sequence[Tuple[str, str]] = (
    ("hit_at_10", "hit@10"),
    ("mrr", "MRR"),
    ("ndcg_at_10", "nDCG@10"),
    ("citation_precision", "cit. prec."),
    ("citation_recall", "cit. rec."),
    ("span_hit_rate", "span hit"),
    ("over_abstain_rate", "over-abst."),
    ("abstention_recall_on_near_misses", "abst. rec."),
    ("p50_ms", "p50 ms"),
    ("p95_ms", "p95 ms"),
    ("cny_per_1k", "CNY/1k"),
)

#: Metrics a bootstrap interval is drawn for, in report order.
INTERVAL_METRICS: Sequence[Tuple[str, str]] = HEADLINE[:8]

#: The factors, short name -> key in a cell's `factors` mapping.
FACTOR_SHORT: Sequence[str] = ("chunk_strategy", "retrieval_mode", "context_mode")

FACTOR_LABELS = {
    "chunk_strategy": "chunk strategy",
    "retrieval_mode": "retrieval",
    "context_mode": "contextualization",
}

#: The paired contrasts the ticket asks for: (factor, treated level, reference level).
CONTRASTS: Sequence[Tuple[str, str, str]] = (
    ("retrieval_mode", "rerank", "hybrid"),
    ("context_mode", "contextual_prefix", "plain"),
    ("context_mode", "late_chunking", "plain"),
)

#: Paired per-item outcomes a contrast is tested on. Each is a claim about a
#: different layer of the system, so a factor can improve one and damage another.
OUTCOMES: Dict[str, str] = {
    "retrieval_hit": "evidence chunk inside the returned depth (answerable items)",
    "grounded_citation": "answered with at least one verified citation (answerable items)",
    "abstention_decision": "answered the answerable, abstained on the near-miss (all items)",
}

DEFAULT_CONFIGS = os.path.join("configs", "grid")
DEFAULT_SOURCES = "reports"
DEFAULT_GOLDEN = os.path.join("golden", "v1.jsonl")
CALIBRATION_DIR = "notes"

MISSING = "missing"


class AggregateError(RuntimeError):
    """The bundle cannot be built from what is on disk, and saying so is the fix."""


# ---- statistics ------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return sum(values) / float(len(values)) if values else 0.0


def _quantile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated quantile of an already sorted sequence."""
    if not values:
        raise ValueError("quantile of an empty sequence")
    if len(values) == 1:
        return float(values[0])
    position = fraction * (len(values) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(values) - 1)
    weight = position - low
    return float(values[low]) * (1.0 - weight) + float(values[high]) * weight


def _cell_seed(cell: str, seed: int) -> int:
    """A per-cell seed independent of iteration order.

    Adding or removing a cell must not change another cell's interval, otherwise a
    table cannot be compared across regenerations.
    """
    return (int(seed) ^ zlib.crc32(cell.encode("utf-8"))) & 0x7FFFFFFF


def _draws(n: int, resamples: int, seed: int) -> List[List[int]]:
    """`resamples` index vectors, each of length `n`, drawn with replacement."""
    rng = random.Random(seed)
    indexes = range(n)
    return [rng.choices(indexes, k=n) for _ in range(resamples)]


def _bootstrap(
    n: int,
    evaluate: Callable[[Sequence[int]], Optional[float]],
    resamples: int,
    seed: int,
    confidence: float,
) -> Dict[str, Any]:
    """The shared resampling loop: one set of item draws, any statistic of them.

    `evaluate` receives one index vector (an item resampled with replacement) and
    returns the statistic for it, or None to drop that resample. Every metric of a
    cell can share the same draws, which is why the loop takes the evaluator rather
    than a column of values.
    """
    if n == 0:
        raise ValueError("bootstrap needs at least one item")
    draws = _draws(n, resamples, seed)
    samples = []
    for picks in draws:
        value = evaluate(picks)
        if value is not None:
            samples.append(float(value))
    if not samples:
        raise ValueError("every resample was unusable, so there is no interval to report")
    samples.sort()
    alpha = 1.0 - confidence
    return {
        "lo": round(_quantile(samples, alpha / 2.0), 6),
        "hi": round(_quantile(samples, 1.0 - alpha / 2.0), 6),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
    }


def bootstrap_mean_ci(
    values: Sequence[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> Dict[str, Any]:
    """Percentile bootstrap interval for the mean of per-item values.

    A constant sample stays constant under every resample, which is what makes it
    a usable check on the resampler itself.
    """
    values = [float(value) for value in values]
    if not values:
        raise ValueError("bootstrap needs at least one value")
    n = len(values)
    getter = values.__getitem__
    summary = _bootstrap(
        n, lambda picks: sum(map(getter, picks)) / n, resamples, seed, confidence
    )
    summary.update({"mean": round(_mean(values), 6), "n": n, "statistic": "mean"})
    return summary


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    label: str,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> Dict[str, Any]:
    """Percentile bootstrap interval for any statistic of per-item values."""
    values = [float(value) for value in values]
    if not values:
        raise ValueError("bootstrap needs at least one value")
    n = len(values)
    getter = values.__getitem__
    summary = _bootstrap(
        n, lambda picks: statistic([getter(index) for index in picks]), resamples, seed, confidence
    )
    summary.update({"mean": round(_mean(values), 6), "n": n, "statistic": label})
    return summary


def bootstrap_ratio_ci(
    numerators: Sequence[float],
    denominators: Sequence[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> Dict[str, Any]:
    """Percentile bootstrap interval for a ratio of sums over resampled items.

    Citation precision is claims-supported over claims-made; claims are not
    independent of their question, so an item brings its whole claim batch into the
    resample and the ratio is taken afterwards.
    """
    numerators = [float(value) for value in numerators]
    denominators = [float(value) for value in denominators]
    if len(numerators) != len(denominators):
        raise ValueError("a ratio needs one denominator per numerator")
    if not numerators:
        raise ValueError("bootstrap needs at least one item")
    total = sum(denominators)
    if total <= 0:
        raise ValueError("a ratio over zero claims has no value to resample")

    numerator_get = numerators.__getitem__
    denominator_get = denominators.__getitem__

    def evaluate(picks: Sequence[int]) -> Optional[float]:
        denominator = sum(map(denominator_get, picks))
        if denominator <= 0:
            return None
        return sum(map(numerator_get, picks)) / denominator

    summary = _bootstrap(len(numerators), evaluate, resamples, seed, confidence)
    summary.update({"ratio": round(sum(numerators) / total, 6), "n": len(numerators)})
    return summary


def mcnemar_exact(b: int, c: int) -> Dict[str, Any]:
    """McNemar's exact test on the discordant pairs of two paired labellings.

    `b` is the number of items only the first system got right, `c` only the
    second. Under the null the discordant pairs are a fair coin, so the two-sided
    p is twice the smaller binomial tail. No discordant pairs means nothing moved:
    p = 1 rather than a division by zero.
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts cannot be negative")
    pairs = int(b) + int(c)
    if pairs == 0:
        return {
            "b": int(b),
            "c": int(c),
            "pairs": 0,
            "statistic": 0.0,
            "p_value": 1.0,
            "method": "exact-binomial",
        }
    smaller = min(int(b), int(c))
    tail = sum(math.comb(pairs, k) for k in range(smaller + 1))
    # Exact rational arithmetic, so a hand-checked 2x2 matches to the last bit.
    p_value = float(min(Fraction(1), Fraction(2 * tail, 2**pairs)))
    statistic = (abs(int(b) - int(c)) - 1) ** 2 / float(pairs)
    return {
        "b": int(b),
        "c": int(c),
        "pairs": pairs,
        "statistic": round(statistic, 6),
        "p_value": p_value,
        "method": "exact-binomial",
    }


def paired_discordance(
    left: Dict[str, bool], right: Dict[str, bool]
) -> Dict[str, Any]:
    """Align two per-item labellings by item id and count the discordant pairs.

    Items measured by only one side are dropped and counted: a pair that does not
    exist cannot be discordant, and quietly pairing by position would invent one.
    """
    common = sorted(set(left) & set(right))
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    b = sum(1 for item in common if left[item] and not right[item])
    c = sum(1 for item in common if right[item] and not left[item])
    return {
        "pairs": len(common),
        "b": b,
        "c": c,
        "unpaired_left": len(only_left),
        "unpaired_right": len(only_right),
        "left_rate": round(sum(1 for item in common if left[item]) / len(common), 6)
        if common
        else None,
        "right_rate": round(sum(1 for item in common if right[item]) / len(common), 6)
        if common
        else None,
        "items": common,
    }


# ---- the design ------------------------------------------------------------


def load_design(configs_dir: str = DEFAULT_CONFIGS) -> Dict[str, Any]:
    """The eighteen cells, each with a digest recomputed from its own YAML.

    `configs/grid/grid.json` is read for row order and for the run name, but its
    stored `config_digest` is only reported as drift: it was computed at emit time
    and stops matching the moment a default in `config.py` moves. The join key is
    always recomputed here, the way `grid.plan()` does it.
    """
    from . import config as config_mod

    manifest = grid.read_manifest(configs_dir)
    order: List[str] = []
    names: Dict[str, str] = {}
    stored: Dict[str, str] = {}
    factors: Dict[str, Dict[str, str]] = {}
    if manifest:
        for entry in manifest.get("cells", []):
            cell = entry["cell"]
            order.append(cell)
            names[cell] = entry.get("run_name", "")
            stored[cell] = entry.get("config_digest", "")
            factors[cell] = dict(entry.get("factors", {}))

    files = {
        os.path.basename(path)[: -len(".yaml")]: path
        for path in grid.config_files([configs_dir])
    }
    if not order:
        order = sorted(files)

    cells: List[Dict[str, Any]] = []
    drift: List[str] = []
    for cell in order:
        path = files.get(cell)
        if path is None:
            raise AggregateError(
                "the manifest names %s but %s holds no %s.yaml -- re-run `python -m "
                "ragqa grid emit`" % (cell, configs_dir, cell)
            )
        cfg = config_mod.load(path)
        digest = grid.config_digest(cfg)
        entry = {
            "cell": cell,
            "factors": factors.get(cell)
            or {
                "chunk_strategy": cfg["chunk.strategy"],
                "retrieval_mode": cfg["retrieval.mode"],
                "context_mode": cfg["context.mode"],
            },
            "run_name": names.get(cell) or cfg["run.name"],
            "config_digest": digest,
            "stored_digest": stored.get(cell, ""),
            "config_path": path,
        }
        if entry["stored_digest"] and entry["stored_digest"] != digest:
            drift.append(cell)
        cells.append(entry)

    return {
        "cells": cells,
        "configs_dir": configs_dir,
        "manifest_present": bool(manifest),
        "digest_drift": drift,
    }


# ---- run directories -------------------------------------------------------


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _digest_of(path: str) -> str:
    return grid._digest_of_run_dir(path)  # one definition of "which config is this"


def scan_runs(runs_root: str) -> Dict[str, Any]:
    """Index the run root: finished runs by digest, plus what is not a run yet.

    A directory whose `metrics.json` is absent is unfinished and a directory whose
    `metrics.json` will not parse is unreadable; neither is a run, and neither is
    silently promoted to one. Later directories win for a repeated digest, because
    a re-run of the same resolved configuration supersedes its predecessor.
    """
    finished: Dict[str, Dict[str, Any]] = {}
    unfinished: Dict[str, List[str]] = {}
    unreadable: Dict[str, List[str]] = {}
    other: List[str] = []
    if not os.path.isdir(runs_root):
        return {
            "finished": finished,
            "unfinished": unfinished,
            "unreadable": unreadable,
            "other": other,
            "root": runs_root,
        }
    for name in sorted(os.listdir(runs_root)):
        path = os.path.join(runs_root, name)
        if not os.path.isdir(path):
            continue
        digest = _digest_of(path)
        if not digest:
            other.append(name)
            continue
        metrics_path = os.path.join(path, "metrics.json")
        if not os.path.isfile(metrics_path):
            unfinished.setdefault(digest, []).append(name)
            continue
        metrics = _read_json(metrics_path)
        if not isinstance(metrics, dict):
            unreadable.setdefault(digest, []).append(name)
            continue
        finished[digest] = {
            "run_id": name,
            "path": path,
            "metrics": metrics,
            "timings": _read_json(os.path.join(path, "timings.json")) or {},
        }
    return {
        "finished": finished,
        "unfinished": unfinished,
        "unreadable": unreadable,
        "other": other,
        "root": runs_root,
    }


def read_working_points(path: str) -> Dict[str, Dict[str, Any]]:
    """The abstention working point of each run directory it applies to.

    `reports/abstention/working-points.json` is written by the abstention sweep and
    names its population in `applies_to_run_ids`. Joining on that list -- rather than
    on a file name or a mode guess -- is what lets a matrix cell print the threshold
    that was calibrated on exactly its own runs.
    """
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {}
    by_run: Dict[str, Dict[str, Any]] = {}
    for mode, entry in sorted((payload.get("modes") or {}).items()):
        if not isinstance(entry, dict):
            continue
        point = {
            "mode": mode,
            "t": _numbers(entry.get("t")),
            "raw_threshold": _numbers(entry.get("raw_threshold")),
            "f1": _numbers(entry.get("f1")),
            "precision": _numbers(entry.get("precision")),
            "recall": _numbers(entry.get("recall")),
            "constraint_feasible": bool(entry.get("constraint_feasible")),
            "items": entry.get("items") or {},
            "generator": entry.get("generator", ""),
            "source": path,
        }
        for run_id in entry.get("applies_to_run_ids") or []:
            by_run[str(run_id)] = point
    return by_run


def _working_point_text(point: Optional[Dict[str, Any]]) -> str:
    if not point:
        return MISSING
    raw = point.get("raw_threshold")
    t = point.get("t")
    if raw is None or t is None:
        return MISSING
    return "t=%.4f raw=%.6g" % (t, raw)


def _numbers(*values: Any) -> Optional[float]:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _cost_per_1k(cost_cny: Any, total_items: Any) -> Optional[float]:
    """The run's own money scaled to 1,000 questions, when it did not record the rate."""
    if not isinstance(cost_cny, (int, float)) or isinstance(cost_cny, bool):
        return None
    questions = total_items if isinstance(total_items, int) and total_items > 0 else 1
    return float(cost_cny) * 1000.0 / questions


def values_of(metrics: Dict[str, Any], timings: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """The headline numbers of one run, read from what it recorded.

    Anything absent stays None so the renderer can print `missing` instead of a
    zero that would enter a mean.
    """
    metrics = metrics or {}
    timings = timings or {}
    retrieval = metrics.get("retrieval") or {}
    citations = metrics.get("citations") or {}
    abstention = metrics.get("abstention") or {}
    system = metrics.get("system") or {}
    return {
        "hit_at_10": _numbers(retrieval.get("recall_at_k"), retrieval.get("hit_rate")),
        "mrr": _numbers(retrieval.get("mrr")),
        "ndcg_at_10": _numbers(retrieval.get("ndcg_at_10")),
        "citation_precision": _numbers(citations.get("citation_precision")),
        "citation_recall": _numbers(citations.get("citation_recall")),
        "span_hit_rate": _numbers(citations.get("span_hit_rate")),
        "over_abstain_rate": _numbers(abstention.get("over_abstain_rate")),
        "abstention_recall_on_near_misses": _numbers(
            abstention.get("abstention_recall_on_negatives")
        ),
        "under_abstain": _numbers(abstention.get("under_abstain")),
        "p50_ms": _numbers(timings.get("p50_ms")),
        "p95_ms": _numbers(timings.get("p95_ms")),
        "cny_per_1k": _numbers(
            system.get("cost_per_1k_questions_cny"),
            _cost_per_1k(system.get("cost_cny"), (metrics.get("items") or {}).get("total")),
        ),
    }


def matrix_rows(
    runs_root: str,
    design: Sequence[Dict[str, Any]],
    runs: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """One row per declared cell, in design order, with its run or a reason.

    The row count is the design's. A cell whose run is absent, unfinished or
    unreadable keeps its row and says so; a run that matches no cell never becomes
    a row (it is listed separately as an orphan).
    """
    index = runs if runs is not None else scan_runs(runs_root)
    rows: List[Dict[str, Any]] = []
    for entry in design:
        digest = entry["config_digest"]
        found = (index["finished"] or {}).get(digest)
        row: Dict[str, Any] = {
            "cell": entry["cell"],
            "factors": dict(entry.get("factors") or {}),
            "run_name": entry.get("run_name", ""),
            "config_digest": digest,
            "stored_digest": entry.get("stored_digest", ""),
            "run_id": "",
            "status": MISSING,
            "values": {},
            "metrics": {},
            "timings": {},
            "threshold": None,
            "items": None,
            "k": None,
            "note": "",
            "run_dir": "",
        }
        if found:
            metrics = found["metrics"]
            timings = found["timings"]
            config = _read_json(os.path.join(found["path"], "config.json")) or {}
            generate = (config.get("generate") or {}) if isinstance(config, dict) else {}
            items = metrics.get("items") or {}
            row.update(
                {
                    "run_id": found["run_id"],
                    "status": "finished",
                    "values": values_of(metrics, timings),
                    "metrics": metrics,
                    "timings": timings,
                    "threshold": _numbers(generate.get("abstain_score_threshold")),
                    "items": items.get("total"),
                    "k": (metrics.get("retrieval") or {}).get("k"),
                    "run_dir": found["path"],
                }
            )
        elif (index["unreadable"] or {}).get(digest):
            row["status"] = "unreadable"
            row["note"] = (
                "a run directory exists for this configuration but its metrics.json will "
                "not parse: %s" % ", ".join(sorted(index["unreadable"][digest]))
            )
        elif (index["unfinished"] or {}).get(digest):
            row["status"] = "unfinished"
            row["note"] = (
                "no metrics.json yet: %s" % ", ".join(sorted(index["unfinished"][digest]))
            )
        else:
            row["note"] = "no run directory for this configuration under %s" % runs_root
        rows.append(row)
    return rows


# ---- per-item outcomes -----------------------------------------------------


def load_golden(path: str = DEFAULT_GOLDEN) -> Dict[str, Dict[str, Any]]:
    """Golden items by id, with the evidence needed to judge a failure.

    Both the quote (a hit is decided by containing it) and its document (a miss is
    "the wrong document" or "the wrong chunk of the right document") are kept.
    """
    golden: Dict[str, Dict[str, Any]] = {}
    if not os.path.isfile(path):
        return golden
    for row in read_jsonl(path):
        evidence = [
            {"doc_id": entry.get("doc_id", ""), "quote": entry.get("quote", "")}
            for entry in row.get("evidence", [])
            if isinstance(entry, dict)
        ]
        golden[row["id"]] = {
            "answerable": bool(row.get("answerable")),
            "quotes": [entry["quote"] for entry in evidence if entry["quote"]],
            "evidence": evidence,
            "tags": list(row.get("tags") or []),
            "type": row.get("type", ""),
            "reference_answer": row.get("reference_answer", ""),
        }
    return golden


def load_run_items(run_dir: str, golden: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One record per golden item, with what the run did to it.

    Returns None when the run wrote no `predictions.jsonl`: there is nothing to
    resample, and an empty vector would be a fabricated zero.
    """
    predictions_path = os.path.join(run_dir, "predictions.jsonl")
    if not os.path.isfile(predictions_path):
        return None
    predictions = read_jsonl(predictions_path)
    if not predictions:
        return None

    chunks_path = os.path.join(run_dir, "chunks.jsonl")
    texts: Dict[str, str] = {}
    if os.path.isfile(chunks_path):
        for chunk in read_jsonl(chunks_path):
            texts[chunk.get("chunk_id", "")] = chunk.get("text", "")

    citations_path = os.path.join(run_dir, "citations.jsonl")
    verdicts: Dict[str, List[Dict[str, Any]]] = {}
    if os.path.isfile(citations_path):
        for row in read_jsonl(citations_path):
            verdicts.setdefault(row.get("item_id", ""), []).append(row)

    items: Dict[str, Dict[str, Any]] = {}
    for prediction in predictions:
        item_id = prediction.get("item_id", "")
        retrieved = []
        for hit in prediction.get("retrieved") or []:
            row = dict(hit)
            # Attach the text only when the chunk set is actually here. Writing "" for
            # a missing chunk made an absent artifact look like an empty one, and a
            # quote search over empty strings silently reports every item as a miss.
            chunk_text = texts.get(hit.get("chunk_id", ""))
            if chunk_text is not None:
                row["text"] = chunk_text
            retrieved.append(row)
        quotes = golden.get(item_id, {}).get("quotes", [])
        claims = verdicts.get(item_id, [])
        supported = sum(1 for claim in claims if claim.get("supported"))
        # `citations.jsonl` stores the generator's own span with -1 as "the model gave
        # none", while the verifier reports a span only when it located the quote in
        # the chunk. Only a non-negative span is a span hit (metrics.json agrees).
        spans = sum(
            1
            for claim in claims
            if isinstance(claim.get("span_start"), int) and claim["span_start"] >= 0
        )
        items[item_id] = {
            "item_id": item_id,
            "answerable": bool(prediction.get("answerable")),
            "abstained": bool(prediction.get("abstained")),
            "retrieved": retrieved,
            "quotes": quotes,
            "claims": len(claims),
            "supported": supported,
            "spans": spans,
            "error_classes": [claim.get("error_class", "") for claim in claims],
            "rank": 0,
        }
    return {"items": items, "text_available": bool(texts), "golden": golden}


def item_outcomes(items: Dict[str, Dict[str, Any]], misses: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Per-item vectors and the recomputed headline rates, from the artifacts.

    Returns a bundle (items, hits, ranks, rates), not the per-item records:
    `baselines.per_item_outcomes` is the other function, and it returns the records.

    A hit is decided by locating the golden evidence quote inside returned chunk
    text after normalisation -- the same rule `evaluate` uses, applied to the same
    rows -- so the matrix and `metrics.json` can be compared rather than trusted.
    """
    misses_set = set(misses or ())
    answerable = [record for record in items.values() if record["answerable"]]
    unanswerable = [record for record in items.values() if not record["answerable"]]

    ranks: Dict[str, int] = {}
    for item_id, record in items.items():
        if record["quotes"] and record["retrieved"] and record["retrieved"][0].get("text") is not None:
            rank = evaluate_mod._first_hit_rank(record["retrieved"], record["quotes"])
        else:
            rank = 0
        if not record["retrieved"] and item_id in misses_set:
            rank = 0
        ranks[item_id] = rank

    # A committed run directory excludes `chunks.jsonl` (it is regenerable and large,
    # `ADR-0003` + the fetch script), so `predictions.jsonl`'s retrieved rows carry a
    # chunk id, doc id, rank and score but **no text**. Locating the evidence quote
    # therefore cannot be done from the run directory at all: assuming it can made
    # every per-item hit false, every retrieval bootstrap interval [0, 0], and every
    # `retrieval_hit` contrast b = c = 0 — a confident zero for a cell whose own
    # metrics.json says 0.85. The recorded `retrieval.misses` list is the exact
    # complement of the hit set inside the answerable items, computed at run time
    # when the text was still in memory, so it is the honest source here.
    text_available = any(
        hit.get("text")
        for record in items.values()
        for hit in record["retrieved"]
    )
    recomputed = text_available
    hits = {item_id: (rank > 0) for item_id, rank in ranks.items()}
    if not recomputed and misses_set:
        hits = {
            item_id: (item_id not in misses_set)
            for item_id, record in items.items()
            if record["answerable"]
        }

    return {
        "items": items,
        "answerable": [record["item_id"] for record in answerable],
        "unanswerable": [record["item_id"] for record in unanswerable],
        "hits": hits,
        "ranks": ranks,
        "hit_source": "recomputed" if recomputed else ("recorded-misses" if misses_set else MISSING),
        "rates": {
            "hit_at_10": _mean([1.0 if hits[record["item_id"]] else 0.0 for record in answerable]),
            "citation_precision": (
                sum(record["supported"] for record in items.values())
                / float(sum(record["claims"] for record in items.values()))
                if sum(record["claims"] for record in items.values())
                else None
            ),
            "citation_recall": _mean(
                [
                    1.0
                    if (record["supported"] > 0 and not record["abstained"])
                    else 0.0
                    for record in answerable
                ]
            ),
            "span_hit_rate": (
                sum(record["spans"] for record in items.values())
                / float(sum(record["claims"] for record in items.values()))
                if sum(record["claims"] for record in items.values())
                else None
            ),
            "over_abstain_rate": _mean(
                [1.0 if record["abstained"] else 0.0 for record in answerable]
            ),
            "abstention_recall_on_near_misses": _mean(
                [1.0 if record["abstained"] else 0.0 for record in unanswerable]
            ),
        },
    }


def cell_intervals(
    cell: str,
    items: Dict[str, Dict[str, Any]],
    rates: Dict[str, Any],
    timings: Dict[str, Any],
    seed: int = BOOTSTRAP_SEED,
) -> Dict[str, Any]:
    """Bootstrap intervals for every headline metric this cell can support."""
    resolved_seed = _cell_seed(cell, seed)
    answerable = [record for record in items.values() if record["answerable"]]
    unanswerable = [record for record in items.values() if not record["answerable"]]
    claims_total = sum(record["claims"] for record in items.values())
    intervals: Dict[str, Any] = {}

    if answerable:
        intervals["hit_at_10"] = bootstrap_mean_ci(
            [1.0 if rates["hits"][record["item_id"]] else 0.0 for record in answerable],
            seed=resolved_seed,
        )
        intervals["over_abstain_rate"] = bootstrap_mean_ci(
            [1.0 if record["abstained"] else 0.0 for record in answerable], seed=resolved_seed
        )
        intervals["citation_recall"] = bootstrap_mean_ci(
            [
                1.0 if (record["supported"] > 0 and not record["abstained"]) else 0.0
                for record in answerable
            ],
            seed=resolved_seed,
        )
        if rates["hit_source"] == "recomputed":
            intervals["mrr"] = bootstrap_mean_ci(
                [
                    1.0 / rates["ranks"][record["item_id"]]
                    if rates["ranks"][record["item_id"]]
                    else 0.0
                    for record in answerable
                ],
                seed=resolved_seed,
            )
            intervals["ndcg_at_10"] = bootstrap_mean_ci(
                [
                    1.0 / math.log2(rates["ranks"][record["item_id"]] + 1)
                    if rates["ranks"][record["item_id"]]
                    else 0.0
                    for record in answerable
                ],
                seed=resolved_seed,
            )
    if unanswerable:
        intervals["abstention_recall_on_near_misses"] = bootstrap_mean_ci(
            [1.0 if record["abstained"] else 0.0 for record in unanswerable], seed=resolved_seed
        )
    if claims_total:
        supported = [record["supported"] for record in items.values() if record["claims"]]
        made = [record["claims"] for record in items.values() if record["claims"]]
        intervals["citation_precision"] = bootstrap_ratio_ci(supported, made, seed=resolved_seed)
        spans = [record["spans"] for record in items.values() if record["claims"]]
        intervals["span_hit_rate"] = bootstrap_ratio_ci(spans, made, seed=resolved_seed)

    latencies = [float(value) for value in (timings.get("per_item_ms") or []) if isinstance(value, (int, float))]
    if latencies:
        intervals["p50_ms"] = bootstrap_ci(
            latencies, lambda sample: _quantile(sorted(sample), 0.5), "median", seed=resolved_seed
        )
        intervals["p95_ms"] = bootstrap_ci(
            latencies, lambda sample: _quantile(sorted(sample), 0.95), "p95", seed=resolved_seed
        )
    return intervals


# ---- main effects and interactions ----------------------------------------


def _finished(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row["status"] == "finished"]


def main_effects(
    rows: Sequence[Dict[str, Any]], factor: str, metric: str
) -> Dict[str, Any]:
    """Mean of `metric` per level of `factor`, over the cells that exist.

    Levels are taken from the design, so a level with no finished cell still gets
    a row -- with no mean and a cell count of zero. Averaging over whatever
    happened to finish is the honest number, but the count has to travel with it
    or the reader cannot tell three cells from one.
    """
    levels: List[str] = []
    for row in rows:
        level = (row.get("factors") or {}).get(factor)
        if level and level not in levels:
            levels.append(level)

    entries = []
    used = 0
    for level in levels:
        cells = [
            row
            for row in _finished(rows)
            if (row.get("factors") or {}).get(factor) == level
            and row["values"].get(metric) is not None
        ]
        values = [row["values"][metric] for row in cells]
        entries.append(
            {
                "level": level,
                "mean": round(_mean(values), 6) if values else None,
                "cells": len(values),
                "run_ids": [row["run_id"] for row in cells],
            }
        )
        used += len(values)
    return {
        "factor": factor,
        "label": FACTOR_LABELS.get(factor, factor),
        "metric": metric,
        "cells": used,
        "levels": entries,
    }


def interaction(
    rows: Sequence[Dict[str, Any]], factor_a: str, factor_b: str, metric: str
) -> Dict[str, Any]:
    """Two-way means plus the interaction term `mu_ij - mu_i. - mu_.j + mu_..`.

    The term is zero when the two factors add up, which is the only reading of
    "the effect of one factor does not depend on the other" that a balanced design
    can support. Unbalanced combinations keep their own cell count, so a corner
    resting on one cell is visible.
    """
    levels_a: List[str] = []
    levels_b: List[str] = []
    for row in rows:
        factors = row.get("factors") or {}
        value_a = factors.get(factor_a)
        value_b = factors.get(factor_b)
        if value_a and value_a not in levels_a:
            levels_a.append(value_a)
        if value_b and value_b not in levels_b:
            levels_b.append(value_b)

    values: Dict[Tuple[str, str], List[float]] = {}
    run_ids: Dict[Tuple[str, str], List[str]] = {}
    for row in _finished(rows):
        factors = row.get("factors") or {}
        value = row["values"].get(metric)
        if value is None:
            continue
        key = (factors.get(factor_a), factors.get(factor_b))
        values.setdefault(key, []).append(value)
        run_ids.setdefault(key, []).append(row["run_id"])

    grand = _mean([value for group in values.values() for value in group])
    margin_a = {
        level: _mean([value for (left, _right), group in values.items() if left == level for value in group])
        or None
        for level in levels_a
    }
    margin_b = {
        level: _mean([value for (_left, right), group in values.items() if right == level for value in group])
        or None
        for level in levels_b
    }

    cells = []
    for level_a in levels_a:
        for level_b in levels_b:
            group = values.get((level_a, level_b), [])
            mean = _mean(group) if group else None
            term = None
            if (
                mean is not None
                and margin_a.get(level_a) is not None
                and margin_b.get(level_b) is not None
            ):
                term = round(mean - margin_a[level_a] - margin_b[level_b] + grand, 6)
            cells.append(
                {
                    "a": level_a,
                    "b": level_b,
                    "mean": round(mean, 6) if mean is not None else None,
                    "cells": len(group),
                    "interaction": term,
                    "run_ids": run_ids.get((level_a, level_b), []),
                }
            )

    return {
        "metric": metric,
        "a": factor_a,
        "b": factor_b,
        "grand_mean": round(grand, 6),
        "levels_a": levels_a,
        "levels_b": levels_b,
        "margin_a": {
            level: (round(value, 6) if value is not None else None)
            for level, value in margin_a.items()
        },
        "margin_b": {
            level: (round(value, 6) if value is not None else None)
            for level, value in margin_b.items()
        },
        "cells": cells,
    }


# ---- paired contrasts ------------------------------------------------------


def _outcomes_for(
    items: Dict[str, Dict[str, Any]], outcome: Dict[str, Any]
) -> Dict[str, Dict[str, bool]]:
    """The three paired labellings, per item, that a contrast is tested on.

    `outcome` is a whole `item_outcomes` result, not its `rates` sub-dict: the
    per-item hit vector lives at the top level, and reading it from `rates` raised
    KeyError as soon as a contrast actually had two finished cells to pair.
    """
    hits = outcome.get("hits") or {}
    hit: Dict[str, bool] = {}
    grounded: Dict[str, bool] = {}
    decision: Dict[str, bool] = {}
    for item_id, record in items.items():
        if record["answerable"]:
            hit[item_id] = bool(hits.get(item_id))
            grounded[item_id] = bool(record["supported"] > 0 and not record["abstained"])
            decision[item_id] = not record["abstained"]
        else:
            decision[item_id] = record["abstained"]
    return {
        "retrieval_hit": hit,
        "grounded_citation": grounded,
        "abstention_decision": decision,
    }


def contrast_strata(
    rows: Sequence[Dict[str, Any]], factor: str, left: str, right: str
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Cells that differ only in `factor`, paired on the other two factors."""
    others = [name for name in FACTOR_SHORT if name != factor]
    groups: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for row in _finished(rows):
        factors = row.get("factors") or {}
        level = factors.get(factor)
        if level not in (left, right):
            continue
        key = (str(factors.get(others[0])), str(factors.get(others[1])))
        groups.setdefault(key, {})[level] = row
    pairs = []
    for key in sorted(groups):
        levels = groups[key]
        if left in levels and right in levels:
            pairs.append((levels[left], levels[right]))
    return pairs


def contrasts(
    rows: Sequence[Dict[str, Any]],
    items_by_run: Dict[str, Dict[str, Any]],
    spec: Sequence[Tuple[str, str, str]] = CONTRASTS,
) -> List[Dict[str, Any]]:
    """McNemar's exact test on each requested factor contrast.

    A contrast is only tested inside a stratum of the other two factors, so the
    pair differs in one thing. Discordant pairs are pooled across strata to get one
    p-value per contrast; each stratum is also printed, because a pooled result that
    rests on one stratum is a different claim from one that holds in all of them.
    """
    entries: List[Dict[str, Any]] = []
    for factor, left, right in spec:
        pairs = contrast_strata(rows, factor, left, right)
        for outcome, description in OUTCOMES.items():
            pooled_b = pooled_c = pooled_pairs = 0
            strata = []
            for left_row, right_row in pairs:
                left_items = items_by_run.get(left_row["run_id"])
                right_items = items_by_run.get(right_row["run_id"])
                if not left_items or not right_items:
                    continue
                left_outcomes = _outcomes_for(left_items["items"], left_items)[outcome]
                right_outcomes = _outcomes_for(right_items["items"], right_items)[outcome]
                discordance = paired_discordance(left_outcomes, right_outcomes)
                test = mcnemar_exact(discordance["b"], discordance["c"])
                pooled_b += discordance["b"]
                pooled_c += discordance["c"]
                pooled_pairs += discordance["pairs"]
                strata.append(
                    {
                        "stratum": "%s=%s"
                        % (
                            ",".join(name for name in FACTOR_SHORT if name != factor),
                            "/".join(
                                str((left_row["factors"] or {}).get(name))
                                for name in FACTOR_SHORT
                                if name != factor
                            ),
                        ),
                        "left_run": left_row["run_id"],
                        "right_run": right_row["run_id"],
                        "pairs": discordance["pairs"],
                        "b": discordance["b"],
                        "c": discordance["c"],
                        "p_value": test["p_value"],
                        "left_rate": discordance["left_rate"],
                        "right_rate": discordance["right_rate"],
                    }
                )
            pooled = mcnemar_exact(pooled_b, pooled_c) if pooled_pairs else mcnemar_exact(0, 0)
            entries.append(
                {
                    "factor": factor,
                    "label": FACTOR_LABELS.get(factor, factor),
                    "left": left,
                    "right": right,
                    "contrast": "%s vs %s (%s)" % (left, right, FACTOR_LABELS.get(factor, factor)),
                    "outcome": outcome,
                    "outcome_description": description,
                    "pairs": pooled_pairs,
                    "b": pooled["b"],
                    "c": pooled["c"],
                    "p_value": pooled["p_value"],
                    "method": pooled["method"],
                    "strata_pairs": len(strata),
                    "strata": strata,
                }
            )
    return entries


# ---- judges ----------------------------------------------------------------


def judge_table(
    rows: Sequence[Dict[str, Any]],
    notes_dir: str = CALIBRATION_DIR,
    runs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Cohen's kappa per verification layer, and the layer that gates reporting.

    The layers are recomputed from `judge-calibration.verdicts.json` against the
    hand labels rather than copied from the metrics file, so a reader can see the
    arithmetic; where the two disagree the disagreement is reported.
    """
    claims_path = os.path.join(notes_dir, "judge-calibration.json")
    verdicts_path = os.path.join(notes_dir, "judge-calibration.verdicts.json")
    extra: List[Dict[str, Any]] = []
    if os.path.isfile(claims_path) and os.path.isfile(verdicts_path):
        calibration = _read_json(claims_path) or {}
        verdicts = _read_json(verdicts_path) or {}
        bar = _numbers(calibration.get("bar")) or 0.0
        claims = [claim for claim in calibration.get("claims", []) if claim.get("claim_id")]
        human = [bool(claim.get("human_label")) for claim in claims]
        for layer, path in (
            ("containment", lambda verdict: verdict.get("containment_ok")),
            ("nli", lambda verdict: (verdict.get("nli") or {}).get("supported")),
            ("judge", lambda verdict: (verdict.get("llm") or {}).get("supported")),
        ):
            predicted = []
            for claim in claims:
                verdict = verdicts.get(claim["claim_id"]) or {}
                predicted.append(path(verdict))
            summary = judges.score_against_human(human, predicted)
            extra.append(
                {
                    "layer": layer,
                    "n": summary["n"],
                    "skipped": summary["skipped"],
                    "agreement": summary["agreement"],
                    "precision": summary["precision"],
                    "recall": summary["recall"],
                    "kappa": summary["kappa"],
                    "tp": summary["tp"],
                    "fp": summary["fp"],
                    "fn": summary["fn"],
                    "tn": summary["tn"],
                    "bar": bar,
                    "gates": bool(summary["kappa"] >= bar) if bar else None,
                }
            )
        calibration_meta = {
            "path": claims_path,
            "claims": len(claims),
            "bar": bar,
            "nli_model": calibration.get("nli_model", ""),
            "judge_model": calibration.get("judge_model", ""),
            "human_supported": sum(1 for label in human if label),
        }
    else:
        calibration_meta = {"path": claims_path, "claims": 0, "bar": 0.0}

    confusion_csv = os.path.join(notes_dir, "judge-confusion.csv")
    confusion_rows: List[Dict[str, Any]] = []
    if os.path.isfile(confusion_csv):
        with open(confusion_csv, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                confusion_rows.append(
                    {
                        "table": row.get("table", ""),
                        "cell": row.get("cell", ""),
                        "count": int(row.get("count") or 0),
                    }
                )

    per_run = []
    for row in _finished(rows):
        grounding = (row["metrics"].get("grounding") or {})
        confusion = grounding.get("judge_confusion")
        if confusion:
            per_run.append({"run_id": row["run_id"], "cell": row["cell"], "grid": confusion})

    # A run directory outside the design can carry the same grid -- the judge smoke
    # test does -- and it is evidence, just not a cell's evidence. Naming it is the
    # difference between "absent" and "present somewhere the matrix does not see".
    outside = []
    if runs:
        grid_run_ids = {row["run_id"] for row in rows if row.get("run_id")}
        for _digest, entry in sorted((runs.get("finished") or {}).items()):
            if entry.get("run_id") in grid_run_ids:
                continue
            confusion = (entry["metrics"].get("grounding") or {}).get("judge_confusion")
            if confusion:
                outside.append({"run_id": entry["run_id"], "grid": confusion})

    gate = "none"
    for entry in extra:
        if entry["layer"] == "judge" and entry["gates"]:
            gate = "judge"
    if gate == "none":
        for entry in extra:
            if entry["layer"] == "nli" and entry["gates"]:
                gate = "nli"
    return {
        "calibration": calibration_meta,
        "layers": extra,
        "gate": gate,
        "confusion": confusion_rows,
        "runs_with_confusion": per_run,
        "confusion_outside_grid": outside,
    }


# ---- cost ------------------------------------------------------------------


def cost_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per cell: tokens by component, money, index size, latency."""
    entries = []
    for row in rows:
        if row["status"] != "finished":
            entries.append(
                {"cell": row["cell"], "run_id": "", "status": row["status"], "components": {}}
            )
            continue
        system = row["metrics"].get("system") or {}
        components = system.get("cost_components") or {}
        entries.append(
            {
                "cell": row["cell"],
                "run_id": row["run_id"],
                "status": "finished",
                "components": components,
                "cost_cny": _numbers(system.get("cost_cny")),
                "cost_per_1k": _numbers(system.get("cost_per_1k_questions_cny")),
                "index_bytes": _numbers(system.get("index_bytes")),
                "chunks_indexed": _numbers(system.get("chunks_indexed")),
                "p50_ms": _numbers(row["timings"].get("p50_ms")),
                "p95_ms": _numbers(row["timings"].get("p95_ms")),
                "generator": system.get("generator_model", ""),
                "embedder": system.get("embedding_model", ""),
                "judge_enabled": system.get("judge_enabled"),
                "index_seconds": _numbers(row["timings"].get("index_build_seconds")),
            }
        )
    return entries


# ---- failure candidates for the hand-inspected taxonomy --------------------


def failure_candidates(
    runs_root: str,
    design: Optional[Sequence[Dict[str, Any]]] = None,
    configs_dir: str = DEFAULT_CONFIGS,
    golden_path: str = DEFAULT_GOLDEN,
) -> List[Dict[str, Any]]:
    """Every observable failure in the finished runs, with the evidence attached.

    `notes/error-taxonomy.md` is written by hand, but the material it classifies is
    assembled here so the same forty rows can be found again: each candidate carries
    the run id, the item, what the run said, the chunk it leaned on, and the
    verification verdict. Nothing here assigns a taxonomy class -- `errors.jsonl`
    only ever carries the containment layer's own strings, and a reader who wants
    the nine classes has to look at the claim.

    Categories are where the failure was *observed*, not what it is: a retrieval
    miss, an abstention that should not have happened (or should have), a claim the
    verifier rejected, and a parse failure are disjoint observations of the same
    finished run.
    """
    if design is None:
        design = load_design(configs_dir)["cells"]
    golden = load_golden(golden_path)
    runs = scan_runs(runs_root)
    rows = matrix_rows(runs_root, design, runs=runs)

    candidates: List[Dict[str, Any]] = []
    for row in rows:
        if row["status"] != "finished":
            continue
        loaded = load_run_items(row["run_dir"], golden)
        if loaded is None:
            continue
        items = loaded["items"]
        by_id = {record["item_id"]: record for record in items.values()}
        misses = ((row["metrics"].get("retrieval") or {}).get("misses")) or []
        chunks = {}
        chunks_path = os.path.join(row["run_dir"], "chunks.jsonl")
        if os.path.isfile(chunks_path):
            for chunk in read_jsonl(chunks_path):
                chunks[chunk.get("chunk_id", "")] = chunk
        citations: Dict[str, List[Dict[str, Any]]] = {}
        citations_path = os.path.join(row["run_dir"], "citations.jsonl")
        if os.path.isfile(citations_path):
            for citation in read_jsonl(citations_path):
                citations.setdefault(citation.get("item_id", ""), []).append(citation)

        for item_id in sorted(by_id):
            record = by_id[item_id]
            evidence = golden.get(item_id, {})
            retrieved = [
                {
                    "rank": hit.get("rank"),
                    "doc_id": hit.get("doc_id", ""),
                    "chunk_id": hit.get("chunk_id", ""),
                    "score": hit.get("score"),
                }
                for hit in record["retrieved"]
            ]
            evidence_docs = {entry["doc_id"] for entry in evidence.get("evidence", [])}
            retrieved_docs = [hit["doc_id"] for hit in retrieved]
            context_budget = _read_json(os.path.join(row["run_dir"], "config.json")) or {}
            context_chunks = (
                ((context_budget.get("llm") or {}).get("context_chunks"))
                if isinstance(context_budget, dict)
                else None
            )
            base = {
                "cell": row["cell"],
                "run_id": row["run_id"],
                "item_id": item_id,
                "answerable": record["answerable"],
                "evidence": evidence.get("evidence", []),
                "retrieved": retrieved,
                "context_chunks": context_chunks,
                "abstained": record["abstained"],
                "top_score": (retrieved[0]["score"] if retrieved else None),
                "threshold": row.get("threshold"),
            }
            if item_id in misses and record["answerable"]:
                candidates.append(
                    dict(
                        base,
                        category="retrieval_miss",
                        evidence_doc_retrieved=bool(evidence_docs & set(retrieved_docs)),
                        evidence_doc_ranks=[
                            hit["rank"] for hit in retrieved if hit["doc_id"] in evidence_docs
                        ],
                    )
                )
            if record["answerable"] and record["abstained"]:
                candidates.append(dict(base, category="over_abstention"))
            if not record["answerable"] and not record["abstained"]:
                candidates.append(
                    dict(
                        base,
                        category="under_abstention",
                        claims=[
                            {
                                "claim_id": claim.get("claim_id"),
                                "quote": claim.get("quote"),
                                "chunk_id": claim.get("chunk_id"),
                                "supported": claim.get("supported"),
                                "error_class": claim.get("error_class"),
                            }
                            for claim in citations.get(item_id, [])
                        ],
                    )
                )
            for claim in citations.get(item_id, []):
                if claim.get("supported"):
                    continue
                chunk = chunks.get(claim.get("chunk_id", "")) or {}
                candidates.append(
                    dict(
                        base,
                        category="claim_rejected",
                        claim_id=claim.get("claim_id"),
                        chunk_id=claim.get("chunk_id"),
                        doc_id=claim.get("doc_id"),
                        error_class=claim.get("error_class"),
                        detail=(claim.get("detail") or "")[:300],
                        quote=claim.get("quote"),
                        span_start=claim.get("span_start"),
                        span_end=claim.get("span_end"),
                        chunk_text=(chunk.get("text") or "")[:1200],
                    )
                )

        errors_path = os.path.join(row["run_dir"], "errors.jsonl")
        if os.path.isfile(errors_path):
            predictions = {
                prediction.get("item_id", ""): prediction
                for prediction in read_jsonl(os.path.join(row["run_dir"], "predictions.jsonl"))
            }
            for error in read_jsonl(errors_path):
                if error.get("class") != "parse_failure":
                    continue
                prediction = predictions.get(error.get("item_id", "")) or {}
                candidates.append(
                    {
                        "category": "parse_failure",
                        "cell": row["cell"],
                        "run_id": row["run_id"],
                        "item_id": error.get("item_id", ""),
                        "error_class": error.get("class"),
                        "detail": error.get("detail"),
                        "raw_response": (prediction.get("raw_response") or "")[:1200],
                    }
                )
    return candidates


# ---- rendering helpers -----------------------------------------------------

def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return ("%." + str(digits) + "f") % value
    return str(value)


def _fmt_bytes(value: Any) -> str:
    if value is None:
        return MISSING
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or unit == "GiB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f GiB" % size


def _write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _write_csv(path: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))
    return path


def _write_json(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def _csv_value(value: Any) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "%.6f" % value
    return str(value)


# ---- the tables ------------------------------------------------------------


def _render_matrix_md(
    rows: Sequence[Dict[str, Any]], design: Dict[str, Any], runs_root: str
) -> str:
    finished = _finished(rows)
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = ["# The 18-cell matrix", ""]
    lines.append(
        "Every row is one declared cell. `%s` means the cell produced no run that could "
        "be read: it is printed, never dropped, so the table always has the design's "
        "row count." % MISSING
    )
    lines.append("")
    lines.append(
        "- runs root: `%s`" % runs_root
    )
    lines.append(
        "- cells: %d declared, %d finished, %d unfinished, %d unreadable, %d absent"
        % (
            len(rows),
            counts.get("finished", 0),
            counts.get("unfinished", 0),
            counts.get("unreadable", 0),
            counts.get(MISSING, 0),
        )
    )
    lines.append(
        "- joined by recomputed config digest, never by timestamp; %d cell(s) carry a "
        "stale digest in `grid.json` (see `matrix.json`)" % len(design.get("digest_drift", []))
    )
    lines.append(
        "- `abst. t` is the cell's own `generate.abstain_score_threshold`; it differs per "
        "retrieval level because each level is scored on its own scale"
    )
    lines.append(
        "- `abstention working point` is the threshold the calibrated sweep chose for that "
        "cell's score scale, joined through `reports/abstention/working-points.json` on the "
        "`applies_to_run_ids` list; `%s` means no sweep covered this cell's run" % MISSING
    )
    lines.append("")
    header = [
        "#",
        "cell",
        "chunk",
        "retrieval",
        "context",
        "run id",
        "items",
        "abst. t",
        "abstention working point",
    ] + [label for _key, label in HEADLINE]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for position, row in enumerate(rows, 1):
        factors = row.get("factors") or {}
        cells = [
            str(position),
            row["cell"],
            str(factors.get("chunk_strategy", "")),
            str(factors.get("retrieval_mode", "")),
            str(factors.get("context_mode", "")),
            row["run_id"] or MISSING,
            _fmt(row.get("items")) if row.get("items") is not None else MISSING,
            _fmt(row.get("threshold"), 4) if row.get("threshold") is not None else MISSING,
            _working_point_text(row.get("working_point")),
        ]
        for key, _label in HEADLINE:
            value = row["values"].get(key) if row["status"] == "finished" else None
            cells.append(_fmt(value, 4) if key not in ("p50_ms", "p95_ms") else _fmt(value, 1))
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("## Main effects")
    lines.append("")
    lines.append(
        "Each mean is over the cells that finished with a non-missing value; the cell "
        "count travels beside it, because a level resting on one cell is not the same "
        "claim as a level resting on six."
    )
    lines.append("")
    for factor in FACTOR_SHORT:
        for metric, label in (("hit_at_10", "hit@10"), ("citation_precision", "citation precision")):
            effects = main_effects(rows, factor, metric)
            lines.append(
                "**%s — %s** (over %d cells)" % (effects["label"], label, effects["cells"])
            )
            lines.append("")
            lines.append("| level | mean | cells | run ids |")
            lines.append("|---|---|---|---|")
            for entry in effects["levels"]:
                lines.append(
                    "| %s | %s | %d | %s |"
                    % (
                        entry["level"],
                        _fmt(entry["mean"], 4) if entry["mean"] is not None else MISSING,
                        entry["cells"],
                        ", ".join(entry["run_ids"]) or MISSING,
                    )
                )
            lines.append("")

    lines.append("## Interactions")
    lines.append("")
    lines.append(
        "The term is `mean(i,j) - mean(i) - mean(j) + grand mean`: zero when the two "
        "factors add up on this metric, and the sign says which corner beats the "
        "additive prediction."
    )
    corners = sum(
        1
        for entry in interaction(rows, "retrieval_mode", "context_mode", "hit_at_10")["cells"]
        if entry["mean"] is not None
    )
    if corners < 4:
        lines.append("")
        lines.append(
            "**Read this as unestimated, not as zero.** Only %d corners of the 2 x 3 x 3 "
            "design have a finished cell, so every term below is zero by construction: an "
            "interaction needs all four corners of its 2 x 2 sub-table before it can say "
            "anything. The cell counts beside each mean are the honest content here." % corners
        )
    lines.append("")
    pairs = (
        ("retrieval_mode", "context_mode"),
        ("chunk_strategy", "retrieval_mode"),
        ("chunk_strategy", "context_mode"),
    )
    for factor_a, factor_b in pairs:
        table = interaction(rows, factor_a, factor_b, "hit_at_10")
        lines.append(
            "**%s x %s — hit@10** (grand mean %s)"
            % (
                FACTOR_LABELS[factor_a],
                FACTOR_LABELS[factor_b],
                _fmt(table["grand_mean"], 4),
            )
        )
        lines.append("")
        header = ["%s \\ %s" % (factor_a, factor_b)] + [
            "%s (n)" % level for level in table["levels_b"]
        ]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for level_a in table["levels_a"]:
            cells = [level_a]
            for level_b in table["levels_b"]:
                found = [
                    entry
                    for entry in table["cells"]
                    if entry["a"] == level_a and entry["b"] == level_b
                ][0]
                if found["mean"] is None:
                    cells.append(MISSING)
                else:
                    cells.append(
                        "%s (%d), i=%s"
                        % (
                            _fmt(found["mean"], 4),
                            found["cells"],
                            _fmt(found["interaction"], 4)
                            if found["interaction"] is not None
                            else MISSING,
                        )
                    )
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        backed = [
            "(%s, %s) -> %s" % (entry["a"], entry["b"], ", ".join(entry["run_ids"]))
            for entry in table["cells"]
            if entry["run_ids"]
        ]
        if backed:
            lines.append("Corners behind the grid above: " + "; ".join(backed) + ".")
            lines.append("")
    return "\n".join(lines) + "\n"


def _render_significance_md(
    rows: Sequence[Dict[str, Any]],
    intervals: Dict[str, Dict[str, Any]],
    contrast_rows: Sequence[Dict[str, Any]],
    resolved_seed_note: str,
) -> str:
    lines = ["# Paired significance and intervals", ""]
    lines.append(
        "- resample unit: **item** (a golden question, not a claim); claims travel with "
        "their item because they are not independent of it"
    )
    lines.append(
        "- bootstrap: %d resamples, seed %d (per cell: seed XOR crc32(cell)), percentile "
        "interval, %.0f%% confidence" % (BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, BOOTSTRAP_CONFIDENCE * 100)
    )
    lines.append(
        "- paired test: McNemar's exact test on discordant pairs, two-sided exact binomial"
    )
    lines.append("- %s" % resolved_seed_note)
    lines.append("")

    lines.append("## Interval per cell and headline metric")
    lines.append("")
    header = ["cell", "run id"] + ["%s [95%% CI]" % label for _key, label in INTERVAL_METRICS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        cell_intervals = intervals.get(row["cell"]) or {}
        cells = [row["cell"], row["run_id"] or MISSING]
        for key, _label in INTERVAL_METRICS:
            value = cell_intervals.get(key)
            if not value:
                cells.append(MISSING)
                continue
            point = value.get("ratio", value.get("mean"))
            cells.append("%s [%s, %s]" % (_fmt(point, 4), _fmt(value["lo"], 4), _fmt(value["hi"], 4)))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Factor contrasts")
    lines.append("")
    lines.append(
        "One pair of cells per stratum of the other two factors; discordant pairs are "
        "pooled within a contrast. `b` counts items only the treated level got right, "
        "`c` only the reference level. `p` is exact, not asymptotic."
    )
    lines.append("")
    header = ["contrast", "outcome", "strata", "pairs", "b", "c", "p", "winner"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for entry in contrast_rows:
        if entry["pairs"] == 0:
            winner = MISSING
            p_value = MISSING
        elif entry["b"] == entry["c"]:
            winner = "tie"
            p_value = _fmt(entry["p_value"], 6)
        else:
            winner = entry["left"] if entry["b"] > entry["c"] else entry["right"]
            p_value = _fmt(entry["p_value"], 6)
        lines.append(
            "| %s | %s | %d | %d | %d | %d | %s | %s |"
            % (
                entry["contrast"],
                entry["outcome"],
                entry["strata_pairs"],
                entry["pairs"],
                entry["b"],
                entry["c"],
                p_value,
                winner,
            )
        )
    lines.append("")
    lines.append(
        "A contrast with no paired cells prints `missing`: the matrix had not finished "
        "both ends of it when this bundle was generated, and inventing a zero would look "
        "like evidence of no difference."
    )
    lines.append("")
    lines.append("## Per-stratum detail")
    lines.append("")
    header = ["contrast", "outcome", "stratum", "left run", "right run", "pairs", "b", "c", "p"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for entry in contrast_rows:
        for stratum in entry["strata"]:
            lines.append(
                "| %s | %s | %s | %s | %s | %d | %d | %d | %s |"
                % (
                    entry["contrast"],
                    entry["outcome"],
                    stratum["stratum"],
                    stratum["left_run"],
                    stratum["right_run"],
                    stratum["pairs"],
                    stratum["b"],
                    stratum["c"],
                    _fmt(stratum["p_value"], 6),
                )
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def _render_judges_md(table: Dict[str, Any]) -> str:
    lines = ["# Judge agreement", ""]
    calibration = table["calibration"]
    lines.append(
        "- hand-labelled calibration set: %d claims (%d labelled supported) at `%s`"
        % (
            calibration.get("claims", 0),
            calibration.get("human_supported", 0),
            calibration.get("path", ""),
        )
    )
    if calibration.get("nli_model"):
        lines.append("- NLI layer: `%s`" % calibration["nli_model"])
    if calibration.get("judge_model"):
        lines.append("- judge layer: `%s`" % calibration["judge_model"])
    lines.append(
        "- agreement bar: kappa >= %s" % _fmt(calibration.get("bar"), 2)
    )
    lines.append(
        "- **layer that gates reporting: %s**" % table["gate"]
    )
    lines.append("")
    lines.append(
        "Kappa is recomputed from the stored verdicts and the hand labels, not copied "
        "from `judge-calibration.metrics.json`. A layer under the bar is reported as "
        "advisory and cannot be the gate."
    )
    lines.append("")
    header = ["layer", "n", "skipped", "agreement", "precision", "recall", "kappa", ">= bar", "role"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for entry in table["layers"]:
        role = "gates reporting" if entry["layer"] == table["gate"] else "advisory"
        lines.append(
            "| %s | %d | %d | %s | %s | %s | %s | %s | %s |"
            % (
                entry["layer"],
                entry["n"],
                entry["skipped"],
                _fmt(entry["agreement"], 4),
                _fmt(entry["precision"], 4),
                _fmt(entry["recall"], 4),
                _fmt(entry["kappa"], 4),
                _fmt(entry["gates"]),
                role,
            )
        )
    lines.append("")
    lines.append("## NLI x judge confusion")
    lines.append("")
    if table["confusion"]:
        header = ["table", "cell", "count"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in table["confusion"]:
            lines.append("| %s | %s | %d |" % (row["table"], row["cell"], row["count"]))
        lines.append("")
        lines.append(
            "`nli_only` is the cell that matters: claims the entailment model passes and "
            "the judge rejects are where a cheap layer would have let a bad citation through."
        )
    else:
        lines.append("No `judge-confusion.csv` was found, so there is no grid to print.")
    lines.append("")
    lines.append("## Confusion recorded inside run directories")
    lines.append("")
    if table["runs_with_confusion"]:
        header = ["run id", "cell", "both", "nli only", "judge only", "neither"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for entry in table["runs_with_confusion"]:
            grid_counts = entry["grid"]
            lines.append(
                "| %s | %s | %d | %d | %d | %d |"
                % (
                    entry["run_id"],
                    entry["cell"],
                    grid_counts.get("both_supported", 0),
                    grid_counts.get("nli_only", 0),
                    grid_counts.get("judge_only", 0),
                    grid_counts.get("neither", 0),
                )
            )
    else:
        lines.append(
            "No finished **grid cell** ran with the judge enabled, so "
            "`grounding.judge_confusion` is absent from every finished grid cell's run "
            "directory. It is not absent from the run root: a run directory outside the "
            "design can carry it, and those are listed below when they do."
        )
        outside = table.get("confusion_outside_grid") or []
        if outside:
            lines.append("")
            lines.append("| run id (not a grid cell) | both | nli only | judge only | neither |")
            lines.append("|---|---|---|---|---|")
            for entry in outside:
                counts = entry["grid"]
                lines.append(
                    "| %s | %d | %d | %d | %d |"
                    % (
                        entry["run_id"],
                        counts.get("both_supported", 0),
                        counts.get("nli_only", 0),
                        counts.get("judge_only", 0),
                        counts.get("neither", 0),
                    )
                )
            lines.append("")
            lines.append(
                "Those rows are judge evidence from outside the matrix: they show the two "
                "layers do run and do disagree, and they are not a cell's numbers, so they "
                "do not enter any headline figure."
            )
        else:
            lines.append(
                "No other run directory under the run root carries one either, so the "
                "calibration set above is the only judge evidence in this snapshot."
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def _render_cost_md(costs: Sequence[Dict[str, Any]]) -> str:
    components = sorted(
        {name for entry in costs for name in (entry.get("components") or {})}
    )
    lines = ["# System cost", ""]
    lines.append(
        "Tokens are the run's own counters, split by the component that spent them. "
        "Money is the run's recorded USD cost converted at the fixed rate in `run.py`; "
        "`CNY/1k` is that figure scaled to 1,000 questions."
    )
    lines.append("")
    header = ["cell", "run id", "generator"]
    for name in components:
        header += ["%s in" % name, "%s out" % name]
    header += ["CNY total", "CNY/1k", "index size", "chunks", "p50 ms", "p95 ms"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for entry in costs:
        cells = [entry["cell"], entry["run_id"] or MISSING, entry.get("generator", "") or MISSING]
        for name in components:
            component = (entry.get("components") or {}).get(name) or {}
            if entry["status"] != "finished":
                cells += [MISSING, MISSING]
            else:
                cells += [_fmt(component.get("tokens_in")), _fmt(component.get("tokens_out"))]
        cells += [
            _fmt(entry.get("cost_cny")) if entry["status"] == "finished" else MISSING,
            _fmt(entry.get("cost_per_1k")) if entry["status"] == "finished" else MISSING,
            _fmt_bytes(entry.get("index_bytes")) if entry["status"] == "finished" else MISSING,
            _fmt(int(entry["chunks_indexed"])) if entry.get("chunks_indexed") else MISSING,
            _fmt(entry.get("p50_ms"), 1) if entry.get("p50_ms") is not None else MISSING,
            _fmt(entry.get("p95_ms"), 1) if entry.get("p95_ms") is not None else MISSING,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "Embedding and reranking run locally, so their cost is electricity rather than "
        "a line item; the money in this table is tokens."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ---- figures ---------------------------------------------------------------


def _figure_note(axis, text: str) -> None:
    axis.text(0.5, 0.5, text, ha="center", va="center", transform=axis.transAxes, fontsize=10)
    axis.set_axis_off()


def draw_family_figure(csv_path: str, out_path: str) -> Optional[str]:
    """One sensitivity family: a line per headline metric against the swept knob.

    Drawn from the CSV ticket 13 wrote, never from the markdown beside it, so the
    figure cannot drift from the table it accompanies.
    """
    if not os.path.isfile(csv_path):
        return None
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # matplotlib is optional; the CSV carries the numbers
        return None

    finished = [row for row in rows if (row.get("status") or "") == "finished"]
    family = rows[0].get("family", os.path.basename(csv_path))
    figure, axis = plt.subplots(figsize=(7.0, 4.0), dpi=140)
    if not finished:
        _figure_note(
            axis,
            "no finished sweep run yet: %d row(s) in %s"
            % (len(rows), os.path.basename(csv_path)),
        )
        axis.set_title("%s sweep (pending)" % family)
    else:
        metric_columns = [
            ("recall_at_k", "hit@k"),
            ("mrr", "MRR"),
            ("ndcg_at_10", "nDCG@10"),
            ("citation_precision", "citation precision"),
            ("citation_recall", "citation recall"),
        ]
        xs: List[float] = []
        series: Dict[str, List[float]] = {name: [] for name, _label in metric_columns}
        for row in sorted(finished, key=lambda item: float(item.get("x") or 0.0)):
            xs.append(float(row.get("x") or 0.0))
            for name, _label in metric_columns:
                raw = row.get(name)
                series[name].append(float(raw) if raw not in (None, "", MISSING) else float("nan"))
        for name, label in metric_columns:
            axis.plot(xs, series[name], marker="o", label=label)
        axis.set_xlabel("swept value")
        axis.set_ylabel("metric")
        axis.set_ylim(0.0, 1.0)
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize=8)
        axis.set_title("%s sweep (%d finished point(s))" % (family, len(finished)))
    figure.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    figure.savefig(out_path, metadata={"Software": None})
    plt.close(figure)
    return out_path


def draw_abstention_figure(csv_path: str, out_path: str) -> Optional[str]:
    """Precision against recall for one abstention curve, from its CSV."""
    if not os.path.isfile(csv_path):
        return None
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    mode = os.path.basename(csv_path)[: -len("-pr.csv")]
    points = []
    for row in rows:
        precision = row.get("precision")
        recall = row.get("recall")
        if precision in (None, "", MISSING) or recall in (None, "", MISSING):
            continue
        points.append((float(recall), float(precision), float(row.get("t") or 0.0)))

    figure, axis = plt.subplots(figsize=(6.0, 4.0), dpi=140)
    if not points:
        _figure_note(axis, "no scorable point in %s" % os.path.basename(csv_path))
        axis.set_title("abstention, %s (pending)" % mode)
    else:
        points.sort()
        axis.plot(
            [point[0] for point in points],
            [point[1] for point in points],
            marker="o",
            label="answer class precision vs recall",
        )
        axis.set_xlabel("recall on answerable items")
        axis.set_ylabel("precision of answered items")
        axis.set_xlim(0.0, 1.05)
        axis.set_ylim(0.0, 1.05)
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize=8)
        axis.set_title("abstention curve, %s (%d points)" % (mode, len(points)))
    figure.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    figure.savefig(out_path, metadata={"Software": None})
    plt.close(figure)
    return out_path


def draw_figures(out: str, sources_root: Optional[str] = DEFAULT_SOURCES) -> List[Dict[str, str]]:
    """Regenerate every figure from the CSVs that carry the numbers.

    Returns the path of each drawing together with the CSV it was drawn from, so
    the list in `figures.md` names the source rather than guessing it back from the
    file name.
    """
    if not sources_root:
        return []
    drawn: List[Dict[str, str]] = []
    figures_dir = os.path.join(out, "figures")
    sweeps_dir = os.path.join(sources_root, "sweeps")
    for family in ("k", "chunk", "hops"):
        source = os.path.join(sweeps_dir, family + ".csv")
        path = draw_family_figure(source, os.path.join(figures_dir, "sweep-%s.png" % family))
        if path:
            drawn.append({"path": path, "source": source})
    abstention_dir = os.path.join(sources_root, "abstention")
    if os.path.isdir(abstention_dir):
        for name in sorted(os.listdir(abstention_dir)):
            if not name.endswith("-pr.csv"):
                continue
            source = os.path.join(abstention_dir, name)
            path = draw_abstention_figure(
                source, os.path.join(figures_dir, "abstention-%s.png" % name[: -len("-pr.csv")])
            )
            if path:
                drawn.append({"path": path, "source": source})
    return drawn


def _csv_point_counts(path: str) -> Tuple[int, int]:
    """How many points in a sweep/abstention CSV are finished, out of how many."""
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return 0, 0
    finished = sum(1 for row in rows if (row.get("status") or "finished") == "finished")
    return finished, len(rows)


def _render_figures_md(
    out: str, sources_root: Optional[str], figures: Sequence[Dict[str, str]]
) -> str:
    lines = ["# Figures", ""]
    lines.append(
        "Every figure here is redrawn from a CSV under `%s`, so the picture and the "
        "table beside it cannot disagree. The CSVs are written by the sweep and "
        "abstention commands; this step only draws." % (sources_root or "(none)")
    )
    lines.append("")
    if not figures:
        lines.append(
            "No source CSV was found, so no figure was drawn. Point `--sources` at the "
            "directory that holds `sweeps/` and `abstention/`."
        )
        lines.append("")
        return "\n".join(lines) + "\n"
    for entry in figures:
        name = os.path.relpath(entry["path"], out).replace(os.sep, "/")
        source = os.path.relpath(entry["source"], sources_root).replace(os.sep, "/")
        finished, total = _csv_point_counts(entry["source"])
        lines.append("## `%s`" % name)
        lines.append("")
        lines.append("![](%s)" % name)
        lines.append("")
        lines.append(
            "Drawn from `%s`: %d of %d point(s) finished." % (source, finished, total)
        )
        lines.append("")
    return "\n".join(lines) + "\n"


# ---- the bundle ------------------------------------------------------------


def _render_readme(
    runs_root: str,
    design: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    files: Sequence[str],
    out: str,
) -> str:
    finished = _finished(rows)
    lines = ["# `reports/` is generated, not written", ""]
    lines.append(
        "Every file in this directory is produced by one command. Editing anything here "
        "by hand creates a number that no run directory backs, which is the one thing "
        "this bundle exists to prevent. Change the code or the runs, then regenerate."
    )
    lines.append("")
    lines.append("```")
    lines.append('python -m ragqa aggregate --runs "%s" --out reports' % runs_root)
    lines.append("```")
    lines.append("")
    lines.append(
        "That is the exact command used to produce this snapshot: %d of %d cells "
        "finished, %d printed as `%s`."
        % (len(finished), len(rows), len(rows) - len(finished), MISSING)
    )
    lines.append("")
    lines.append("## What each file answers")
    lines.append("")
    answers = [
        ("matrix.md", "the 18-cell table, main effects per factor, and two-way interactions"),
        ("matrix.csv", "the same cells, one row per cell, for a spreadsheet or a plot"),
        ("matrix.json", "the cells plus every effect table and the join metadata, for code"),
        ("significance.md", "bootstrap intervals per cell and McNemar on the factor contrasts"),
        ("significance.csv", "the same intervals and contrasts, machine readable"),
        ("judges.md", "Cohen's kappa per verification layer and the NLI x judge confusion grid"),
        ("judges.csv", "the per-layer calibration numbers"),
        ("cost.md", "tokens by component, CNY per 1,000 questions, index size, latency"),
        ("cost.csv", "the same cost table, machine readable"),
        ("figures.md", "which figure was drawn from which CSV"),
        ("figures/*.png", "sensitivity and abstention curves, redrawn from the CSVs"),
    ]
    lines.append("| file | answers |")
    lines.append("|---|---|")
    for name, question in answers:
        lines.append("| `%s` | %s |" % (name, question))
    lines.append("")
    lines.append("## Protocol this bundle assumes")
    lines.append("")
    lines.append(
        "- a cell is joined to its run by the config digest recomputed from the cell's "
        "YAML; the digest stored in `configs/grid/grid.json` is reported as drift, not used"
    )
    lines.append(
        "- intervals: %d bootstrap resamples, seed %d, resample unit = item"
        % (BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED)
    )
    lines.append("- paired tests: McNemar's exact test, two-sided")
    lines.append(
        "- a directory with no `metrics.json` is not a run; the cell is printed as `%s`"
        % MISSING
    )
    lines.append("")
    lines.append("## Files in this snapshot")
    lines.append("")
    for name in files:
        lines.append("- `%s`" % os.path.relpath(name, out).replace(os.sep, "/"))
    lines.append("")
    return "\n".join(lines) + "\n"


def regenerate(
    runs_root: str,
    out: str,
    design: Optional[Sequence[Dict[str, Any]]] = None,
    design_meta: Optional[Dict[str, Any]] = None,
    configs_dir: str = DEFAULT_CONFIGS,
    sources_root: Optional[str] = DEFAULT_SOURCES,
    golden_path: str = DEFAULT_GOLDEN,
    notes_dir: str = CALIBRATION_DIR,
) -> Dict[str, Any]:
    """Build the whole bundle under `out`; return what was written and what it says.

    `design` may be passed in (tests and non-standard trees); otherwise the cells
    come from `configs_dir` with their digests recomputed.
    """
    meta = dict(design_meta or {})
    if design is None:
        loaded = load_design(configs_dir)
        design = loaded["cells"]
        meta = {
            "configs_dir": loaded["configs_dir"],
            "manifest_present": loaded["manifest_present"],
            "digest_drift": loaded["digest_drift"],
        }
    meta.setdefault("digest_drift", [])

    runs = scan_runs(runs_root)
    rows = matrix_rows(runs_root, design, runs=runs)

    # Each cell prints the abstention working point calibrated on its own runs, so a
    # reader can compare the threshold a cell used with the one its scale supports.
    working_points = read_working_points(os.path.join(out, "abstention", "working-points.json"))
    for row in rows:
        row["working_point"] = working_points.get(row.get("run_id") or "")

    golden = load_golden(golden_path)
    items_by_run: Dict[str, Dict[str, Any]] = {}
    outcomes_by_cell: Dict[str, Dict[str, Any]] = {}
    intervals: Dict[str, Dict[str, Any]] = {}
    drift: List[Dict[str, Any]] = []
    for position, row in enumerate(rows):
        if row["status"] != "finished":
            continue
        loaded_items = load_run_items(row["run_dir"], golden)
        if loaded_items is None:
            row["note"] = "no predictions.jsonl in %s" % row["run_dir"]
            continue
        misses = ((row["metrics"].get("retrieval") or {}).get("misses")) or []
        outcome = item_outcomes(loaded_items["items"], misses)
        outcome["text_available"] = loaded_items["text_available"]
        items_by_run[row["run_id"]] = outcome
        outcomes_by_cell[row["cell"]] = outcome
        cell_ci = cell_intervals(row["cell"], loaded_items["items"], outcome, row["timings"])
        intervals[row["cell"]] = cell_ci

        # Recomputation is a check on metrics.json, not a replacement for it.
        for key, label in HEADLINE[:8]:
            recorded = row["values"].get(key)
            recomputed = outcome["rates"].get(key)
            if recorded is None or recomputed is None:
                continue
            if abs(float(recorded) - float(recomputed)) > 5e-3:
                drift.append(
                    {
                        "cell": row["cell"],
                        "run_id": row["run_id"],
                        "metric": key,
                        "metrics_json": float(recorded),
                        "recomputed": round(float(recomputed), 6),
                    }
                )

    contrast_rows = contrasts(rows, items_by_run)
    judge_rows = judge_table(rows, notes_dir=notes_dir, runs=runs)
    costs = cost_rows(rows)

    os.makedirs(out, exist_ok=True)
    written: List[str] = []

    # matrix.md / .csv / .json
    matrix_md = _render_matrix_md(rows, meta, runs_root)
    written.append(_write(os.path.join(out, "matrix.md"), matrix_md))

    header = [
        "cell",
        "chunk_strategy",
        "retrieval_mode",
        "context_mode",
        "run_id",
        "status",
        "items",
        "k",
        "abstain_threshold",
        "abstention_working_point",
        "abstention_working_point_raw",
    ] + [key for key, _label in HEADLINE]
    matrix_csv_rows = []
    for row in rows:
        factors = row.get("factors") or {}
        values = [
            row["cell"],
            factors.get("chunk_strategy", ""),
            factors.get("retrieval_mode", ""),
            factors.get("context_mode", ""),
            row["run_id"] or MISSING,
            row["status"],
            "" if row.get("items") is None else row["items"],
            "" if row.get("k") is None else row["k"],
            _csv_value(row.get("threshold")),
            ""
            if not row.get("working_point")
            else _csv_value(row["working_point"].get("t")),
            ""
            if not row.get("working_point")
            else _csv_value(row["working_point"].get("raw_threshold")),
        ]
        for key, _label in HEADLINE:
            values.append(
                _csv_value(row["values"].get(key)) if row["status"] == "finished" else MISSING
            )
        matrix_csv_rows.append(values)
    written.append(
        _write_csv(os.path.join(out, "matrix.csv"), header, matrix_csv_rows)
    )

    effects = {}
    for factor in FACTOR_SHORT:
        for key, _label in HEADLINE:
            effects["%s:%s" % (factor, key)] = main_effects(rows, factor, key)
    interactions = {}
    for factor_a, factor_b in (
        ("retrieval_mode", "context_mode"),
        ("chunk_strategy", "retrieval_mode"),
        ("chunk_strategy", "context_mode"),
    ):
        for key, _label in HEADLINE:
            interactions["%s:%s:%s" % (factor_a, factor_b, key)] = interaction(
                rows, factor_a, factor_b, key
            )

    matrix_json = {
        "schema": "ragqa.aggregate/1",
        "protocol": {
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_confidence": BOOTSTRAP_CONFIDENCE,
            "resample_unit": "item",
            "paired_test": "mcnemar-exact-two-sided",
            "missing_marker": MISSING,
        },
        "runs_root": runs_root,
        "design": {
            "configs_dir": meta.get("configs_dir", configs_dir),
            "manifest_present": meta.get("manifest_present"),
            "digest_drift": meta.get("digest_drift", []),
            "cells": len(rows),
        },
        "cells": [
            {
                "cell": row["cell"],
                "factors": row.get("factors") or {},
                "run_name": row.get("run_name", ""),
                "config_digest": row.get("config_digest", ""),
                "stored_digest": row.get("stored_digest", ""),
                "run_id": row["run_id"],
                "status": row["status"],
                "items": row.get("items"),
                "k": row.get("k"),
                "abstain_threshold": row.get("threshold"),
                "values": row["values"] if row["status"] == "finished" else {},
                "note": row.get("note", ""),
            }
            for row in rows
        ],
        "orphan_runs": sorted(runs["other"]),
        "unfinished_runs": sorted(
            name for names in runs["unfinished"].values() for name in names
        ),
        "unreadable_runs": sorted(
            name for names in runs["unreadable"].values() for name in names
        ),
        "effects": effects,
        "interactions": interactions,
        "drift": drift,
        "intervals": intervals,
        "contrasts": contrast_rows,
    }
    written.append(_write_json(os.path.join(out, "matrix.json"), matrix_json))

    # significance
    seed_note = (
        "the seed is fixed per cell as `%d XOR crc32(cell)`; a cell added later does not "
        "move another cell's interval" % BOOTSTRAP_SEED
    )
    written.append(
        _write(
            os.path.join(out, "significance.md"),
            _render_significance_md(rows, intervals, contrast_rows, seed_note),
        )
    )
    significance_header = [
        "cell",
        "run_id",
        "metric",
        "point",
        "lo",
        "hi",
        "resamples",
        "seed",
    ]
    significance_rows = []
    for row in rows:
        cell_ci = intervals.get(row["cell"]) or {}
        for key, _label in INTERVAL_METRICS:
            interval = cell_ci.get(key)
            if not interval:
                significance_rows.append(
                    [row["cell"], row["run_id"] or MISSING, key, MISSING, MISSING, MISSING, "", ""]
                )
                continue
            significance_rows.append(
                [
                    row["cell"],
                    row["run_id"],
                    key,
                    _csv_value(interval.get("ratio", interval.get("mean"))),
                    _csv_value(interval["lo"]),
                    _csv_value(interval["hi"]),
                    interval["resamples"],
                    interval["seed"],
                ]
            )
    for entry in contrast_rows:
        significance_rows.append(
            [
                "%s|%s" % (entry["contrast"], entry["outcome"]),
                "%s/%s" % (entry["left"], entry["right"]),
                "mcnemar_p",
                _csv_value(entry["p_value"]),
                _csv_value(entry["b"]),
                _csv_value(entry["c"]),
                entry["pairs"],
                "",
            ]
        )
    written.append(
        _write_csv(
            os.path.join(out, "significance.csv"), significance_header, significance_rows
        )
    )

    # judges
    written.append(_write(os.path.join(out, "judges.md"), _render_judges_md(judge_rows)))
    judge_header = ["layer", "n", "skipped", "agreement", "precision", "recall", "kappa", "bar", "gates"]
    written.append(
        _write_csv(
            os.path.join(out, "judges.csv"),
            judge_header,
            [
                [
                    entry["layer"],
                    entry["n"],
                    entry["skipped"],
                    _csv_value(entry["agreement"]),
                    _csv_value(entry["precision"]),
                    _csv_value(entry["recall"]),
                    _csv_value(entry["kappa"]),
                    _csv_value(entry["bar"]),
                    _csv_value(entry["gates"]),
                ]
                for entry in judge_rows["layers"]
            ],
        )
    )

    # cost
    written.append(_write(os.path.join(out, "cost.md"), _render_cost_md(costs)))
    component_names = sorted({name for entry in costs for name in (entry.get("components") or {})})
    cost_header = ["cell", "run_id", "status", "generator"]
    for name in component_names:
        cost_header += ["%s_in" % name, "%s_out" % name, "%s_usd" % name]
    cost_header += ["cost_cny", "cost_per_1k_cny", "index_bytes", "chunks", "p50_ms", "p95_ms"]
    cost_csv_rows = []
    for entry in costs:
        values = [entry["cell"], entry["run_id"] or MISSING, entry["status"], entry.get("generator", "")]
        for name in component_names:
            component = (entry.get("components") or {}).get(name) or {}
            values += [
                _csv_value(component.get("tokens_in")),
                _csv_value(component.get("tokens_out")),
                _csv_value(component.get("usd")),
            ]
        values += [
            _csv_value(entry.get("cost_cny")),
            _csv_value(entry.get("cost_per_1k")),
            _csv_value(entry.get("index_bytes")),
            _csv_value(entry.get("chunks_indexed")),
            _csv_value(entry.get("p50_ms")),
            _csv_value(entry.get("p95_ms")),
        ]
        cost_csv_rows.append(values)
    written.append(_write_csv(os.path.join(out, "cost.csv"), cost_header, cost_csv_rows))

    # figures
    figures = draw_figures(out, sources_root)
    written.append(_write(os.path.join(out, "figures.md"), _render_figures_md(out, sources_root, figures)))
    written.extend(entry["path"] for entry in figures)

    # README last: it lists the files it sits beside.
    written.append(
        _write(
            os.path.join(out, "README.md"),
            _render_readme(runs_root, meta, rows, written + [os.path.join(out, "README.md")], out),
        )
    )

    return {
        "out": out,
        "files": written,
        "rows": rows,
        "matrix": matrix_json,
        "contrasts": contrast_rows,
        "judges": judge_rows,
        "costs": costs,
        "figures": figures,
        "drift": drift,
        "runs": runs,
    }


def command(runs_root: str = "runs", out: str = "reports") -> int:
    """`python -m ragqa aggregate --runs <root> --out <dir>`."""
    if not os.path.isdir(runs_root):
        print("PROBLEM no runs root at %s" % runs_root, file=sys.stderr)
        return 1
    try:
        result = regenerate(runs_root, out)
    except AggregateError as error:
        print("PROBLEM %s" % error, file=sys.stderr)
        return 1

    rows = result["rows"]
    finished = [row for row in rows if row["status"] == "finished"]
    print(
        "aggregate: %d of %d cell(s) finished, %d missing"
        % (len(finished), len(rows), len(rows) - len(finished))
    )
    drift = result["matrix"]["design"]["digest_drift"]
    if drift:
        print(
            "note: %d cell(s) carry a stale digest in configs/grid/grid.json (recomputed "
            "from YAML for every join): %s" % (len(drift), ", ".join(drift))
        )
    if result["drift"]:
        for entry in result["drift"]:
            print(
                "DRIFT %s %s: metrics.json says %s, artifacts say %s"
                % (entry["cell"], entry["metric"], entry["metrics_json"], entry["recomputed"])
            )
    for row in rows:
        print(
            "  %-52s %-11s %s"
            % (row["cell"], row["status"], row["run_id"] or MISSING)
        )
    print(
        "wrote %d file(s) under %s (seed %d, %d resamples, unit = item)"
        % (len(result["files"]), out, BOOTSTRAP_SEED, BOOTSTRAP_RESAMPLES)
    )
    return 0

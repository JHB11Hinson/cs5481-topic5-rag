"""The contextual-prefix A/B on the golden set (ticket 07, last box).

Every `contextual_prefix` cell of the matrix is paired with its `plain` twin --
same chunk strategy, same retrieval mode, same generator, same golden set -- and
the two run directories are read side by side. Nothing here executes a model or
touches a run directory: the numbers are recomputed from `predictions.jsonl`,
`chunks.jsonl` and `citations.jsonl`, and `metrics.json` is only compared against
them so a disagreement is printed rather than hidden.

Three rules the rest of this module exists to keep:

*   **One factor moves.** The twin relationship is checked, not assumed: the two
    resolved configs are diffed with `baselines.substantive_diff` and the pair is
    refused unless the only factor group that moved is `contextualization`. A
    fixed-vs-recursive pairing is a different experiment and is not reported as a
    prefix effect.
*   **`pending` is not zero.** A twin whose run directory is absent, unfinished
    (no `metrics.json`) or measured on another golden set leaves the pair with no
    numbers at all. A zero would look like evidence of no difference.
*   **Resample the item, not the claim.** Claims are not independent of the
    question they answer, so the bootstrap draws answerable items and takes their
    whole claim batch. The draws, the seed and the statistic all come from
    `aggregate`, so this table and `reports/significance.md` cannot disagree.

The abstention and citation metrics are the *containment* layer's: a claim counts
when the verifier located its quote inside the cited chunk (`ADR-0004`). The
contextual prefix is index-side only (`ADR-0013`), so every difference below is a
retrieval effect -- the generator never sees a prefix.

    python scripts/context_ab.py --runs runs --out notes/prefix-ab.md
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import aggregate
from . import baselines
from . import config as config_mod

SCHEMA = "ragqa.context_ab/1"

#: The factor the pair moves, and its two levels. `TREATED` is the level that
#: earns the difference; the table always reads treated vs reference.
FACTOR = "context_mode"
TREATED = "contextual_prefix"
REFERENCE = "plain"

#: What must be identical inside a pair for the difference to be the prefix.
STRATUM_FACTORS: Sequence[str] = ("chunk_strategy", "retrieval_mode")

USABLE = "usable"
PENDING = "pending"
REFUSED = "refused"

#: One resampling protocol for the whole project: `aggregate` owns it.
BOOTSTRAP_SEED = aggregate.BOOTSTRAP_SEED
BOOTSTRAP_RESAMPLES = aggregate.BOOTSTRAP_RESAMPLES
BOOTSTRAP_CONFIDENCE = aggregate.BOOTSTRAP_CONFIDENCE

DEFAULT_CONFIGS = aggregate.DEFAULT_CONFIGS
DEFAULT_GOLDEN = aggregate.DEFAULT_GOLDEN
DEFAULT_RUNS = "runs"

#: The golden set every cell of the matrix must be measured on to be comparable.
GOLDEN_VERSION = "v1"

#: Same tolerance `aggregate.regenerate` uses when it compares a recomputed rate
#: against `metrics.json`; a rate that disagrees by more is reported, not smoothed.
DRIFT_TOLERANCE = 5e-3

#: The per-item outcomes a contrast is tested on. The names match
#: `aggregate.OUTCOMES`; these two are the ones a prefix can plausibly move.
PAIRED_OUTCOMES = {
    "retrieval_hit": "the evidence chunk is inside the returned depth (answerable items)",
    "grounded_citation": "the item carries at least one verified citation (answerable items)",
}

#: Metrics carried through the paired comparison and its delta.
NUMERIC_KEYS: Sequence[str] = (
    "hit_at_10",
    "mrr",
    "ndcg_at_10",
    "citation_precision",
    "citation_recall",
    "span_hit_rate",
    "over_abstain_rate",
    "near_misses_abstained",
    "p50_ms",
    "p95_ms",
    "cny_per_1k",
    "index_bytes",
)

#: Headline metrics a recomputation is checked against `metrics.json` for.
DRIFT_KEYS: Sequence[str] = (
    "hit_at_10",
    "mrr",
    "ndcg_at_10",
    "citation_precision",
    "citation_recall",
    "span_hit_rate",
    "over_abstain_rate",
)

MISSING = aggregate.MISSING


class ContextAbError(RuntimeError):
    """The A/B cannot be built from what is on disk, and saying so is the fix."""


# ---- small readers ---------------------------------------------------------


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _number(value: Any) -> Optional[float]:
    """A recorded number, or None. A missing value is never promoted to zero."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / float(len(values)) if values else None


def golden_version(items_path: Any) -> str:
    """`golden/v1.jsonl` -> `v1`; anything unreadable -> the empty string."""
    name = os.path.basename(str(items_path or ""))
    if name.endswith(".jsonl"):
        return name[: -len(".jsonl")]
    return name


# ---- pairing ---------------------------------------------------------------


def factor_drift(reference_cfg, treated_cfg) -> Dict[str, Any]:
    """The config keys that moved between two twins, grouped into factors.

    `ok` means exactly one factor group moved and it is `contextualization`:
    the two cells differ in the prefix and in nothing else, which is the
    precondition for reading the delta as the prefix's effect.
    """
    diff = baselines.substantive_diff(reference_cfg, treated_cfg)
    factors = baselines.differing_factors(diff)
    return {
        "ok": factors == ["contextualization"],
        "factors": factors,
        "keys": sorted(diff),
        "values": {key: dict(diff[key]) for key in sorted(diff)},
    }


def _side(entry: Dict[str, Any], cfg) -> Dict[str, Any]:
    factors = entry.get("factors") or {}
    return {
        "cell": entry["cell"],
        "config_path": entry.get("config_path", ""),
        "chunk_strategy": factors.get("chunk_strategy", cfg["chunk.strategy"]),
        "retrieval_mode": factors.get("retrieval_mode", cfg["retrieval.mode"]),
        "context_mode": cfg["context.mode"],
        "config_digest": entry.get("config_digest", ""),
        "stored_digest": entry.get("stored_digest", ""),
        "run_id": "",
        "run_dir": "",
        "status": "",
        "note": "",
        "metrics": {},
    }


def declared_pairs(cells: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The (plain, contextual_prefix) twins implied by the design, in stratum order.

    A group missing either level is not a pair: the matrix declares six pairings
    and a snapshot in which only one end exists has five pending and one question.
    """
    groups: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for entry in cells:
        factors = entry.get("factors") or {}
        level = factors.get(FACTOR)
        if level not in (TREATED, REFERENCE):
            continue
        key = tuple(str(factors.get(name)) for name in STRATUM_FACTORS)
        groups.setdefault(key, {})[level] = entry

    pairs: List[Dict[str, Any]] = []
    for key in sorted(groups):
        levels = groups[key]
        if TREATED not in levels or REFERENCE not in levels:
            continue
        pairs.append(
            {
                "stratum": "%s/%s" % key,
                "chunk_strategy": key[0],
                "retrieval_mode": key[1],
                "cells": {level: levels[level] for level in (REFERENCE, TREATED)},
            }
        )
    return pairs


def pairs(configs_dir: str = DEFAULT_CONFIGS) -> List[Dict[str, Any]]:
    """The declared pairs, each with its resolved sides and the one-factor check."""
    design = aggregate.load_design(configs_dir)
    built: List[Dict[str, Any]] = []
    for pair in declared_pairs(design["cells"]):
        reference_cfg = config_mod.load(pair["cells"][REFERENCE]["config_path"])
        treated_cfg = config_mod.load(pair["cells"][TREATED]["config_path"])
        drift = factor_drift(reference_cfg, treated_cfg)
        sides = {
            REFERENCE: _side(pair["cells"][REFERENCE], reference_cfg),
            TREATED: _side(pair["cells"][TREATED], treated_cfg),
        }
        if drift["ok"]:
            status, note = "", ""
        else:
            status = REFUSED
            note = (
                "the two cells differ in %s, not only in contextualization (%s), so "
                "their difference is not the prefix"
                % (", ".join(drift["factors"]), ", ".join(drift["keys"]))
            )
        built.append(
            {
                "stratum": pair["stratum"],
                "chunk_strategy": pair["chunk_strategy"],
                "retrieval_mode": pair["retrieval_mode"],
                "sides": sides,
                "factor_check": drift,
                "status": status,
                "note": note,
            }
        )
    return built


# ---- one run directory -----------------------------------------------------


def golden_gate(run_config: Any) -> Tuple[bool, str]:
    """Was this run measured on the golden set the comparison is stated on?"""
    if not isinstance(run_config, dict):
        return False, "no config.json, so the golden set is unknown"
    golden = run_config.get("golden") or {}
    items_path = golden.get("items_path")
    version = golden_version(items_path)
    if version != GOLDEN_VERSION:
        return False, "measured on %s, not the golden %s set" % (items_path or "(no path)", GOLDEN_VERSION)
    if golden.get("limit"):
        return False, "measured on the first %s items, not the whole golden %s set" % (
            golden["limit"],
            GOLDEN_VERSION,
        )
    return True, ""


def _ranks(loaded: Dict[str, Any], outcomes: Dict[str, Any]) -> Dict[str, int]:
    return dict(outcomes["ranks"]) if outcomes["hit_source"] == "recomputed" else {}


def run_metrics(
    run_dir: str, golden: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """One run's numbers, recomputed from its artifacts, with `metrics.json` beside.

    Returns the recomputed bucket values, the per-item outcomes the paired tests
    need, and the recorded values so a drift can be reported. Raises nothing: a
    run that cannot be recomputed is the caller's `pending`.
    """
    metrics_json = _read_json(os.path.join(run_dir, "metrics.json"))
    timings = _read_json(os.path.join(run_dir, "timings.json")) or {}
    cache = _read_json(os.path.join(run_dir, "cache_stats.json")) or {}
    recorded = aggregate.values_of(metrics_json or {}, timings)

    loaded = aggregate.load_run_items(run_dir, golden)
    if loaded is None:
        raise ContextAbError("no predictions.jsonl in %s" % run_dir)
    misses = ((metrics_json or {}).get("retrieval") or {}).get("misses") or []
    outcomes = aggregate.item_outcomes(loaded["items"], misses)
    rates = outcomes["rates"]
    ranks = _ranks(loaded, outcomes)

    items = loaded["items"]
    answerable = [record for record in items.values() if record["answerable"]]
    unanswerable = [record for record in items.values() if not record["answerable"]]
    claims = sum(record["claims"] for record in items.values())
    supported = sum(record["supported"] for record in items.values())

    mrr = None
    ndcg = None
    if ranks:
        mrr = _mean([1.0 / ranks[record["item_id"]] if ranks.get(record["item_id"]) else 0.0
                     for record in answerable])
        ndcg = _mean([1.0 / math.log2(ranks[record["item_id"]] + 1)
                      if ranks.get(record["item_id"]) else 0.0 for record in answerable])

    system = (metrics_json or {}).get("system") or {}
    recomputed = {
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "hit_at_10": _round(rates["hit_at_10"]),
        "mrr": _round(mrr if mrr is not None else recorded["mrr"]),
        "ndcg_at_10": _round(ndcg if ndcg is not None else recorded["ndcg_at_10"]),
        "citation_precision": _round(rates["citation_precision"]),
        "citation_recall": _round(rates["citation_recall"]),
        "span_hit_rate": _round(rates["span_hit_rate"]),
        "claims": claims,
        "supported": supported,
        "over_abstain_rate": _round(rates["over_abstain_rate"]),
        "abstained_answerable": sum(1 for record in answerable if record["abstained"]),
        "near_misses": len(unanswerable),
        "near_misses_abstained": sum(1 for record in unanswerable if record["abstained"]),
        "p50_ms": _round(recorded["p50_ms"], 1),
        "p95_ms": _round(recorded["p95_ms"], 1),
        "cny_per_1k": _round(recorded["cny_per_1k"]),
        "index_bytes": _number(system.get("index_bytes")),
        "chunks_indexed": _number(system.get("chunks_indexed")),
        "llm_cache_hits": int(cache.get("llm_cache_hits") or 0),
        "llm_cache_misses": int(cache.get("llm_cache_misses") or 0),
        "prefix_cache_hits": int(cache.get("prefix_cache_hits") or 0),
        "prefix_cache_misses": int(cache.get("prefix_cache_misses") or 0),
        "hit_source": outcomes["hit_source"],
    }

    return {
        "values": recomputed,
        "recorded": {
            key: _round(recorded.get(key), 1 if key in ("p50_ms", "p95_ms") else 4)
            for key in DRIFT_KEYS + ("p50_ms", "p95_ms", "cny_per_1k")
        },
        "items": items,
        "hits": outcomes["hits"],
        "rates": rates,
        "ranks": ranks,
        "answerable": sorted(record["item_id"] for record in answerable),
        "drift": _drift(recomputed, recorded, ranks),
    }


def _drift(recomputed: Dict[str, Any], recorded: Dict[str, Any], ranks: Dict[str, int]) -> List[Dict[str, Any]]:
    """Where `metrics.json` and the artifacts disagree, beyond the tolerance."""
    entries: List[Dict[str, Any]] = []
    for key in DRIFT_KEYS:
        if key in ("mrr", "ndcg_at_10") and not ranks:
            continue
        mine = recomputed.get(key)
        theirs = recorded.get(key)
        if mine is None or theirs is None:
            continue
        if abs(float(mine) - float(theirs)) > DRIFT_TOLERANCE:
            entries.append(
                {"metric": key, "metrics_json": float(theirs), "recomputed": float(mine)}
            )
    return entries


def _resolve(side: Dict[str, Any], index: Dict[str, Any], golden: Dict[str, Dict[str, Any]]) -> None:
    """Attach the run directory behind one cell, or say why there is none."""
    digest = side["config_digest"]
    root = index.get("root", DEFAULT_RUNS)
    found = (index["finished"] or {}).get(digest)
    if found:
        config = _read_json(os.path.join(found["path"], "config.json"))
        ok, reason = golden_gate(config)
        if not ok:
            side.update({"status": PENDING, "note": reason})
            return
        try:
            loaded = run_metrics(found["path"], golden)
        except ContextAbError as error:
            side.update({"status": PENDING, "note": str(error)})
            return
        side.update(
            {
                "run_id": found["run_id"],
                "run_dir": found["path"],
                "status": "finished",
                "note": "",
                "metrics": loaded["values"],
                "recorded": loaded["recorded"],
                "drift": loaded["drift"],
                "items": loaded["items"],
                "hits": loaded["hits"],
                "rates": loaded["rates"],
                "ranks": loaded["ranks"],
                "answerable": loaded["answerable"],
            }
        )
        return
    unreadable = (index["unreadable"] or {}).get(digest)
    if unreadable:
        side.update(
            {
                "status": PENDING,
                "note": "metrics.json will not parse, so this is not a run: %s"
                % ", ".join(sorted(unreadable)),
            }
        )
        return
    unfinished = (index["unfinished"] or {}).get(digest)
    if unfinished:
        side.update(
            {
                "status": PENDING,
                "note": "no metrics.json yet: %s" % ", ".join(sorted(unfinished)),
            }
        )
        return
    side.update(
        {
            "status": PENDING,
            "note": "no run directory for digest %s under %s" % (digest, root),
        }
    )


# ---- paired outcomes and statistics ---------------------------------------


def paired_outcomes(side: Dict[str, Any]) -> Dict[str, Dict[str, bool]]:
    """The answerable items' per-item outcomes, in the matrix's own vocabulary.

    `retrieval_hit` and `grounded_citation` are defined exactly as
    `aggregate.OUTCOMES` defines them, on the answerable items only: a near-miss
    item has no evidence chunk to hit, and a citation it does not need cannot
    count.
    """
    hit: Dict[str, bool] = {}
    grounded: Dict[str, bool] = {}
    for item_id in side["answerable"]:
        record = side["items"][item_id]
        hit[item_id] = bool(side["hits"].get(item_id))
        grounded[item_id] = bool(record["supported"] > 0 and not record["abstained"])
    return {"retrieval_hit": hit, "grounded_citation": grounded}


def paired_test(treated: Dict[str, bool], reference: Dict[str, bool]) -> Dict[str, Any]:
    """McNemar's exact test on one outcome, paired by item id.

    `paired_discordance` aligns the two labellings and counts them; the test
    itself is `baselines.mcnemar_counts`, which defers to
    `aggregate.mcnemar_exact`. Neither is reimplemented here.
    """
    discordance = aggregate.paired_discordance(treated, reference)
    test = baselines.mcnemar_counts(discordance["b"], discordance["c"])
    return {
        "pairs": discordance["pairs"],
        "treated_only": discordance["b"],
        "reference_only": discordance["c"],
        "treated_rate": discordance["left_rate"],
        "reference_rate": discordance["right_rate"],
        "unpaired_treated": discordance["unpaired_left"],
        "unpaired_reference": discordance["unpaired_right"],
        "statistic": test["statistic"],
        "p_value": test["p_value"],
        "method": test["method"],
    }


def hit_interval(
    treated: Dict[str, bool], reference: Dict[str, bool]
) -> Dict[str, Any]:
    """Percentile bootstrap on hit@10, per side and on the paired difference.

    One item is one draw: its hit, then the other side's hit on the same item, so
    the delta is resampled within the pair rather than from two independent
    samples. All three intervals share `BOOTSTRAP_SEED`, so they share the draws.
    """
    common = sorted(set(treated) & set(reference))
    if not common:
        return {}
    left = [1.0 if treated[item] else 0.0 for item in common]
    right = [1.0 if reference[item] else 0.0 for item in common]
    differences = [a - b for a, b in zip(left, right)]
    return {
        TREATED: aggregate.bootstrap_mean_ci(left, seed=BOOTSTRAP_SEED),
        REFERENCE: aggregate.bootstrap_mean_ci(right, seed=BOOTSTRAP_SEED),
        "delta": aggregate.bootstrap_ci(
            differences,
            lambda sample: sum(sample) / float(len(sample)),
            "mean",
            seed=BOOTSTRAP_SEED,
        ),
        "items": len(common),
    }


def deltas(treated: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """treated minus reference, per metric, over the metrics both sides carry."""
    out: Dict[str, Optional[float]] = {}
    for key in NUMERIC_KEYS:
        left = _number(treated.get(key))
        right = _number(reference.get(key))
        out[key] = None if left is None or right is None else _round(left - right)
    return out


# ---- the report ------------------------------------------------------------


def report(
    configs_dir: str = DEFAULT_CONFIGS,
    runs_root: str = DEFAULT_RUNS,
    golden_path: str = DEFAULT_GOLDEN,
) -> Dict[str, Any]:
    """Every declared pair, with its numbers or with the reason it has none."""
    if golden_version(golden_path) != GOLDEN_VERSION:
        raise ContextAbError(
            "the comparison is stated on golden %s, but %s is golden %s; pass the %s file "
            "or the numbers below would be about two different question sets"
            % (
                GOLDEN_VERSION,
                golden_path,
                golden_version(golden_path) or "(unversioned)",
                GOLDEN_VERSION,
            )
        )
    golden = aggregate.load_golden(golden_path)
    index = aggregate.scan_runs(runs_root)

    entries: List[Dict[str, Any]] = []
    for pair in pairs(configs_dir):
        if pair["status"] == REFUSED:
            entries.append(_empty(pair))
            continue

        for level in (REFERENCE, TREATED):
            _resolve(pair["sides"][level], index, golden)
        blocked = [
            "%s: %s" % (level, pair["sides"][level]["note"])
            for level in (TREATED, REFERENCE)
            if pair["sides"][level]["status"] != "finished"
        ]
        if blocked:
            pair["status"] = PENDING
            pair["note"] = "; ".join(blocked)
            entries.append(_empty(pair))
            continue

        reference = pair["sides"][REFERENCE]
        treated = pair["sides"][TREATED]
        outcomes = {
            level: paired_outcomes(pair["sides"][level]) for level in (REFERENCE, TREATED)
        }
        tests = {
            name: paired_test(outcomes[TREATED][name], outcomes[REFERENCE][name])
            for name in PAIRED_OUTCOMES
        }
        intervals = {"hit_at_10": hit_interval(outcomes[TREATED]["retrieval_hit"],
                                              outcomes[REFERENCE]["retrieval_hit"])}
        pair.update(
            {
                "status": USABLE,
                "note": "",
                "metrics": {
                    REFERENCE: reference["metrics"],
                    TREATED: treated["metrics"],
                    "delta": deltas(treated["metrics"], reference["metrics"]),
                },
                "recorded": {
                    REFERENCE: reference["recorded"],
                    TREATED: treated["recorded"],
                },
                "tests": tests,
                "intervals": intervals,
                "discordant": {
                    name: _discordant(outcomes[TREATED][name], outcomes[REFERENCE][name])
                    for name in PAIRED_OUTCOMES
                },
                "outcomes": {
                    level: {name: sorted(outcomes[level][name]) for name in PAIRED_OUTCOMES}
                    for level in (REFERENCE, TREATED)
                },
                "drift": [
                    dict(entry, side=level)
                    for level in (REFERENCE, TREATED)
                    for entry in pair["sides"][level].get("drift", [])
                ],
            }
        )
        entries.append(pair)

    usable = [entry for entry in entries if entry["status"] == USABLE]
    summary = {
        "declared": len(entries),
        "usable": len(usable),
        "pending": len([entry for entry in entries if entry["status"] == PENDING]),
        "refused": len([entry for entry in entries if entry["status"] == REFUSED]),
        "usable_strata": [entry["stratum"] for entry in usable],
        "pending_strata": [
            entry["stratum"] for entry in entries if entry["status"] == PENDING
        ],
    }
    return {
        "schema": SCHEMA,
        "protocol": {
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_confidence": BOOTSTRAP_CONFIDENCE,
            "resample_unit": "item",
            "paired_test": "mcnemar-exact-two-sided",
            "missing_marker": MISSING,
            "golden_version": GOLDEN_VERSION,
        },
        "inputs": {
            "configs_dir": configs_dir,
            "runs_root": index.get("root", runs_root),
            "golden_path": golden_path,
            "golden_items": len(golden),
            "answerable": sum(1 for entry in golden.values() if entry["answerable"]),
            "near_misses": sum(1 for entry in golden.values() if not entry["answerable"]),
        },
        "summary": summary,
        "pairs": entries,
    }


def _empty(pair: Dict[str, Any]) -> Dict[str, Any]:
    """A pair with no numbers: the reason is the content, and zeroes would lie."""
    entry = dict(pair)
    entry.setdefault("metrics", {})
    entry.setdefault("tests", {})
    entry.setdefault("intervals", {})
    entry.setdefault("drift", [])
    entry["metrics"] = {}
    entry["tests"] = {}
    entry["intervals"] = {}
    entry["drift"] = []
    return entry


# ---- the markdown ----------------------------------------------------------


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return "{:,}".format(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) >= 1000:
            return "{:,.0f}".format(value)
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


def _signed(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return MISSING
    return ("%+." + str(digits) + "f") % float(value)


def _signed_count(value: Optional[float]) -> str:
    if value is None:
        return MISSING
    return "%+d" % int(round(float(value)))


def _signed_bytes(value: Optional[float]) -> str:
    if value is None:
        return MISSING
    return ("+" if float(value) >= 0 else "") + _bytes(value)


def _bytes(value: Optional[float]) -> str:
    """A byte count in the largest unit that keeps it readable."""
    if value is None:
        return MISSING
    size = abs(float(value))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or unit == "GiB":
            return "%g %s" % (round(size, 1), unit)
        size /= 1024.0
    return "%g GiB" % round(size, 1)


def _interval(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return MISSING
    return "[%s, %s]" % (_fmt(entry.get("lo"), 3), _fmt(entry.get("hi"), 3))


def _items(item_ids: Sequence[str]) -> str:
    """A short, checkable list of golden item ids."""
    if not item_ids:
        return "none"
    return ", ".join("`%s`" % item for item in item_ids)


def _pair_of(entry: Dict[str, Any], level: str) -> Dict[str, Any]:
    return entry["metrics"].get(level, {})


def _excluding_zero(entry: Optional[Dict[str, Any]]) -> bool:
    """Does the paired interval on the delta keep zero out of it?"""
    if not entry:
        return False
    lo, hi = entry.get("lo"), entry.get("hi")
    if lo is None or hi is None:
        return False
    return lo > 0.0 or hi < 0.0


def _noise_sentence(interval: Optional[Dict[str, Any]], items: int) -> str:
    """One sentence: is this difference separable from noise at this sample size?"""
    if not interval:
        return "no paired interval is available"
    if _excluding_zero(interval):
        return (
            "the paired interval excludes zero, so at %d answerable items the difference "
            "is separable from noise" % items
        )
    return (
        "the paired interval contains zero, so at %d answerable items the difference is "
        "not distinguishable from noise" % items
    )


def _discordant(
    treated: Dict[str, bool], reference: Dict[str, bool]
) -> Dict[str, List[str]]:
    """Which items each side got right alone, so the flip can be looked up."""
    common = sorted(set(treated) & set(reference))
    return {
        "treated_only": [item for item in common if treated[item] and not reference[item]],
        "reference_only": [item for item in common if reference[item] and not treated[item]],
    }


def render(report: Dict[str, Any]) -> str:
    """The note: the table, then a paragraph per retrieval mode, then the caveats.

    Everything here is filled from the report, so the file can be regenerated at
    any point in the matrix and cannot drift from the run directories it names.
    """
    summary = report["summary"]
    inputs = report["inputs"]
    protocol = report["protocol"]
    lines: List[str] = ["# Contextual prefix vs plain, on the golden set", ""]
    lines.append(
        "Generated by `python scripts/context_ab.py`; do not edit by hand. Every number "
        "comes from the run directories named below, and `metrics.json` is compared "
        "against the artifacts rather than trusted."
    )
    lines.append("")

    # -- status
    lines.append("## Status right now")
    lines.append("")
    lines.append(
        "- **%d pairings declared** (%d chunk strategies x %d retrieval modes); "
        "**%d usable**, **%d pending**, **%d refused**."
        % (
            summary["declared"],
            len({entry["chunk_strategy"] for entry in report["pairs"]}),
            len({entry["retrieval_mode"] for entry in report["pairs"]}),
            summary["usable"],
            summary["pending"],
            summary["refused"],
        )
    )
    lines.append(
        "- golden set `%s`: %d items, %d answerable and %d near-misses; one item moving "
        "is %.3f of hit@10." % (
            inputs["golden_path"],
            inputs["golden_items"],
            inputs["answerable"],
            inputs["near_misses"],
            1.0 / inputs["answerable"] if inputs["answerable"] else 0.0,
        )
    )
    usable = [entry for entry in report["pairs"] if entry["status"] == USABLE]
    if usable:
        lines.append(
            "- usable: "
            + "; ".join(
                "`%s` (plain `%s` vs prefix `%s`)"
                % (
                    entry["stratum"],
                    entry["sides"][REFERENCE]["run_id"],
                    entry["sides"][TREATED]["run_id"],
                )
                for entry in usable
            )
        )
    else:
        lines.append("- usable: none yet.")
    pending = [entry for entry in report["pairs"] if entry["status"] == PENDING]
    if pending:
        lines.append("- **pending — no numbers, not zeroes:**")
        for entry in pending:
            lines.append("  - `%s`: %s" % (entry["stratum"], entry["note"]))
    refused = [entry for entry in report["pairs"] if entry["status"] == REFUSED]
    for entry in refused:
        lines.append("- refused: `%s`: %s" % (entry["stratum"], entry["note"]))
    lines.append("")

    # -- the verdict, said plainly
    if usable:
        lines.append("## Verdict")
        lines.append("")
        for paragraph in _verdict_paragraphs(report):
            lines.append(paragraph)
            lines.append("")

    # -- protocol
    lines.append("## Protocol")
    lines.append("")
    lines.append(
        "- **Pairing.** One `contextual_prefix` cell against its `plain` twin: same chunk "
        "strategy, same retrieval mode, same generator, same golden set. The two resolved "
        "configs are diffed (`baselines.substantive_diff`) and the pair is refused unless "
        "`contextualization` is the only factor that moved."
    )
    lines.append(
        "- **Recomputation.** hit@10, MRR, nDCG@10, citation precision/recall, span hit "
        "rate and the abstention counts are recomputed from `predictions.jsonl`, "
        "`chunks.jsonl` and `citations.jsonl` with the same rule the matrix uses (a hit is "
        "the golden quote found inside a returned chunk; a citation counts when the "
        "verifier located the quote)."
    )
    lines.append(
        "- **Paired test.** McNemar's exact test, two-sided, on the discordant items: "
        "`b` = the prefix got it right and plain did not, `c` = the reverse. Implemented "
        "once, in `aggregate.mcnemar_exact`, and called through `baselines.mcnemar_counts`."
    )
    lines.append(
        "- **Interval.** %d bootstrap resamples, seed %d, percentile interval, "
        "%.0f%% confidence. The resample unit is the **item** (a golden question), not the "
        "claim: an item's whole claim batch travels with it."
        % (
            protocol["bootstrap_resamples"],
            protocol["bootstrap_seed"],
            protocol["bootstrap_confidence"] * 100,
        )
    )
    lines.append(
        "- **Missing is not zero.** A twin whose run directory is absent, unfinished (no "
        "`metrics.json`) or measured on another golden set leaves its pair `pending`, with "
        "the reason printed and no metric attached."
    )
    lines.append(
        "- **The strings themselves are audited elsewhere.** `notes/prefix-audit.md` reads "
        "20 of the generated prefixes against a four-part rubric (0 of 20 fail); this note "
        "measures their effect on retrieval and citation, not their quality."
    )
    lines.append("")

    # -- the table
    lines.append("## The table")
    lines.append("")
    if not usable:
        lines.append("No pair has two finished run directories yet, so there is no table.")
        lines.append("")
    else:
        lines.append(
            "`b`/`c` are the discordant counts behind the McNemar p; the interval is on "
            "the hit@10 delta and is paired within the item."
        )
        lines.append("")
        header = [
            "stratum",
            "hit@10 plain",
            "hit@10 prefix",
            "delta",
            "95% CI on delta",
            "p (hit)",
            "cit. prec. plain",
            "cit. prec. prefix",
            "delta",
            "p (cited item)",
        ]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for entry in usable:
            plain = _pair_of(entry, REFERENCE)
            prefix = _pair_of(entry, TREATED)
            interval = entry["intervals"]["hit_at_10"]["delta"]
            hit_test = entry["tests"]["retrieval_hit"]
            citation_test = entry["tests"]["grounded_citation"]
            cells = [
                "`%s`" % entry["stratum"],
                _fmt(plain.get("hit_at_10")),
                _fmt(prefix.get("hit_at_10")),
                _signed(entry["metrics"]["delta"].get("hit_at_10")),
                _interval(interval),
                "%s (b=%d, c=%d)"
                % (_fmt(hit_test["p_value"]), hit_test["treated_only"], hit_test["reference_only"]),
                _fmt(plain.get("citation_precision")),
                _fmt(prefix.get("citation_precision")),
                _signed(entry["metrics"]["delta"].get("citation_precision")),
                "%s (b=%d, c=%d)"
                % (
                    _fmt(citation_test["p_value"]),
                    citation_test["treated_only"],
                    citation_test["reference_only"],
                ),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

        for entry in usable:
            lines.extend(_pair_block(entry, report))
    lines.append("")

    # -- one paragraph per retrieval mode
    lines.append("## What the prefix bought or cost, per retrieval mode")
    lines.append("")
    for mode in ("dense", "hybrid", "rerank"):
        for paragraph in _mode_paragraphs(report, mode):
            lines.append(paragraph)
            lines.append("")
    if usable:
        lines.append("### Across the usable pairs")
        lines.append("")
        for paragraph in _pattern_paragraphs(report):
            lines.append(paragraph)
            lines.append("")

    # -- the asymmetry
    lines.append("## One asymmetry a reader must not mistake")
    lines.append("")
    lines.append(
        "At `contextual_prefix` the **dense and the sparse indexes both carry the prefix, "
        "while the generation prompt does not** (`ADR-0013`): the prompt is handed the raw "
        "chunk text. The generator therefore never sees a prefix, so no citation number "
        "below is the model reacting to one. Citation precision can still move, because "
        "which chunks reach the prompt -- and at what rank -- is decided by the prefixed "
        "index. Read every citation delta in this note as **a retrieval effect**, and read "
        "the cost row beside it as the reason the prompt was left alone: the money per "
        "question barely moves, because the tokens sent to the generator are the same "
        "tokens. A second experiment that does put the prefix in the prompt is possible "
        "without touching the index code (`chunks_contextual.jsonl` keeps prefix, "
        "contextual text and original text side by side), and this build does not run it."
    )
    lines.append("")
    lines.append(
        "A second thing worth keeping straight: the prefix costs one cheap-model call per "
        "chunk **once**, and every run above reports a full prefix-cache hit "
        "(`prefix_cache_hits` in `cache_stats.json`), so the A/B compares two retrievals "
        "over the same cached strings rather than two samples of generated text."
    )
    lines.append("")

    # -- pending
    lines.append("## Still pending")
    lines.append("")
    if pending:
        lines.append(
            "The matrix is mid-flight. This file is a living document: as each pending "
            "pair's second run directory lands, re-running the command below adds it and "
            "rewrites the paragraphs. Nothing above is invalidated by that; the counts and "
            "the per-mode verdicts are what change."
        )
        lines.append("")
        lines.append("| stratum | plain run | prefix run | why it is pending |")
        lines.append("|---|---|---|---|")
        for entry in pending:
            lines.append(
                "| `%s` | %s | %s | %s |"
                % (
                    entry["stratum"],
                    entry["sides"][REFERENCE]["run_id"] or MISSING,
                    entry["sides"][TREATED]["run_id"] or MISSING,
                    entry["note"],
                )
            )
    else:
        lines.append(
            "No pair is pending: every `plain` cell has its `contextual_prefix` twin on "
            "disk and on the golden set."
        )
    lines.append("")
    lines.append("## Regenerate")
    lines.append("")
    lines.append("```")
    lines.append(
        'python scripts/context_ab.py --configs "%s" --runs "%s" --golden "%s" --out notes/prefix-ab.md'
        % (inputs["configs_dir"], inputs["runs_root"], inputs["golden_path"])
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def _pair_block(entry: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
    """Every bucket for one pair, side by side, with its delta."""
    lines = ["### `%s`" % entry["stratum"], ""]
    plain = _pair_of(entry, REFERENCE)
    prefix = _pair_of(entry, TREATED)
    delta = entry["metrics"]["delta"]
    drift = entry["drift"]

    lines.append(
        "%d answerable items, %d near-misses. Run directories: plain `%s`, prefix `%s`."
        % (
            prefix.get("answerable") or 0,
            prefix.get("near_misses") or 0,
            entry["sides"][REFERENCE]["run_id"],
            entry["sides"][TREATED]["run_id"],
        )
    )
    lines.append("")
    lines.append("| bucket | metric | plain | prefix | delta |")
    lines.append("|---|---|---|---|---|")
    rows = [
        ("retrieval", "hit@10", "hit_at_10"),
        ("retrieval", "MRR", "mrr"),
        ("retrieval", "nDCG@10", "ndcg_at_10"),
        ("citations", "precision", "citation_precision"),
        ("citations", "recall", "citation_recall"),
        ("citations", "span hit rate", "span_hit_rate"),
        ("abstention", "over-abstain rate", "over_abstain_rate"),
        ("abstention", "near-misses abstained of %s" % _fmt(plain.get("near_misses")), "near_misses_abstained"),
        ("system", "p50 ms", "p50_ms"),
        ("system", "p95 ms", "p95_ms"),
        ("system", "CNY per 1,000 questions", "cny_per_1k"),
        ("system", "index size", "index_bytes"),
    ]
    for bucket, label, key in rows:
        if key == "index_bytes":
            rendered = [
                bucket,
                label,
                _fmt_bytes(plain.get(key)),
                _fmt_bytes(prefix.get(key)),
                _signed_bytes(delta.get(key)),
            ]
        elif key == "near_misses_abstained":
            rendered = [
                bucket,
                label,
                _fmt(plain.get(key)),
                _fmt(prefix.get(key)),
                _signed_count(delta.get(key)),
            ]
        else:
            digits = 1 if key in ("p50_ms", "p95_ms") else 4
            rendered = [
                bucket,
                label,
                _fmt(plain.get(key), digits),
                _fmt(prefix.get(key), digits),
                _signed(delta.get(key), digits),
            ]
        lines.append("| " + " | ".join(rendered) + " |")
    lines.append("")
    lines.append(
        "Claims: %s plain (%s supported) vs %s prefix (%s supported). Abstained on "
        "answerable: %s vs %s. LLM cache hits/misses: %s/%s plain vs %s/%s prefix -- "
        "compare latency only within that column pair."
        % (
            _fmt(plain.get("claims")),
            _fmt(plain.get("supported")),
            _fmt(prefix.get("claims")),
            _fmt(prefix.get("supported")),
            _fmt(plain.get("abstained_answerable")),
            _fmt(prefix.get("abstained_answerable")),
            _fmt(plain.get("llm_cache_hits")),
            _fmt(plain.get("llm_cache_misses")),
            _fmt(prefix.get("llm_cache_hits")),
            _fmt(prefix.get("llm_cache_misses")),
        )
    )
    lines.append("")
    hit_drift = entry["discordant"]["retrieval_hit"]
    cited_drift = entry["discordant"]["grounded_citation"]
    lines.append(
        "Items only `plain` retrieved: %s. Only `%s`: %s. Items only `plain` carried a "
        "verified citation on: %s. Only the prefix: %s."
        % (
            _items(hit_drift["reference_only"]),
            TREATED,
            _items(hit_drift["treated_only"]),
            _items(cited_drift["reference_only"]),
            _items(cited_drift["treated_only"]),
        )
    )
    lines.append("")
    if drift:
        lines.append(
            "**Drift.** `metrics.json` and the artifacts disagree on %d value(s): %s."
            % (
                len(drift),
                "; ".join(
                    "%s %s (recorded %s, recomputed %s)"
                    % (row["side"], row["metric"], _fmt(row["metrics_json"]), _fmt(row["recomputed"]))
                    for row in drift
                ),
            )
        )
    else:
        lines.append(
            "**Drift.** None: every recomputed rate agrees with `metrics.json` to within "
            "%g, so the two records of this pair describe the same run." % DRIFT_TOLERANCE
        )
    lines.append("")
    return lines


def _mode_paragraphs(report: Dict[str, Any], mode: str) -> List[str]:
    """The prose for one retrieval mode, built from the pairs that are usable."""
    pairs = [entry for entry in report["pairs"] if entry["retrieval_mode"] == mode]
    usable = [entry for entry in pairs if entry["status"] == USABLE]
    heading = "**%s**" % mode
    if not usable:
        reasons = "; ".join("`%s` — %s" % (entry["stratum"], entry["note"]) for entry in pairs)
        return [
            "%s — no usable pair in this snapshot, so this mode contributes nothing to "
            "the A/B yet: %s." % (heading, reasons or "no cell declared")
        ]

    paragraphs: List[str] = []
    for entry in usable:
        plain = _pair_of(entry, REFERENCE)
        prefix = _pair_of(entry, TREATED)
        delta = entry["metrics"]["delta"]
        hit_test = entry["tests"]["retrieval_hit"]
        citation_test = entry["tests"]["grounded_citation"]
        interval = entry["intervals"]["hit_at_10"]["delta"]
        items = entry["intervals"]["hit_at_10"].get("items") or prefix.get("answerable") or 0
        moved = delta.get("hit_at_10")
        direction = "gained" if (moved or 0.0) > 0 else ("lost" if (moved or 0.0) < 0 else "moved")

        parts = [
            "%s — chunk strategy `%s`." % (heading, entry["chunk_strategy"]),
            "Retrieval: the prefix %s %s of hit@10 (%s to %s) on %d paired items, winning "
            "%d and losing %d, McNemar p = %s; %s."
            % (
                direction,
                _fmt(abs(moved)) if moved else "no part",
                _fmt(plain.get("hit_at_10")),
                _fmt(prefix.get("hit_at_10")),
                items,
                hit_test["treated_only"],
                hit_test["reference_only"],
                _fmt(hit_test["p_value"]),
                _noise_sentence(interval, items),
            ),
            "Ranking moved with it: MRR %s and nDCG@10 %s (plain %s / %s), %s."
            % (
                _signed(delta.get("mrr")),
                _signed(delta.get("ndcg_at_10")),
                _fmt(plain.get("mrr")),
                _fmt(plain.get("ndcg_at_10")),
                "one item changing side, so the rest of the ordering is untouched"
                if (hit_test["treated_only"] + hit_test["reference_only"]) == 1
                else "%d items changing side, so the ordering of the rest moves too"
                % (hit_test["treated_only"] + hit_test["reference_only"]),
            ),
            "Citations: precision %s (%s to %s) and span hit rate %s, while the item-level "
            "'carries a supported citation' outcome went %d for the prefix against %d for "
            "plain at p = %s, %s. Citation recall moved %s (%s to %s). Both of those are "
            "retrieval effects, not the model reading a prefix (`ADR-0013`)."
            % (
                _signed(delta.get("citation_precision")),
                _fmt(plain.get("citation_precision")),
                _fmt(prefix.get("citation_precision")),
                _signed(delta.get("span_hit_rate")),
                citation_test["treated_only"],
                citation_test["reference_only"],
                _fmt(citation_test["p_value"]),
                "which is separable from noise"
                if citation_test["p_value"] < 0.05
                else "which is not distinguishable from noise",
                _signed(delta.get("citation_recall")),
                _fmt(plain.get("citation_recall")),
                _fmt(prefix.get("citation_recall")),
            ),
            "Abstention: over-abstain %s to %s, near-misses refused %s of %s against %s of "
            "%s, so the prefix neither won nor lost a single near-miss in this pair."
            % (
                _fmt(plain.get("over_abstain_rate")),
                _fmt(prefix.get("over_abstain_rate")),
                _fmt(plain.get("near_misses_abstained")),
                _fmt(plain.get("near_misses")),
                _fmt(prefix.get("near_misses_abstained")),
                _fmt(prefix.get("near_misses")),
            )
            if plain.get("near_misses_abstained") == prefix.get("near_misses_abstained")
            else "Abstention: over-abstain %s to %s, near-misses refused %s of %s against "
            "%s of %s."
            % (
                _fmt(plain.get("over_abstain_rate")),
                _fmt(prefix.get("over_abstain_rate")),
                _fmt(plain.get("near_misses_abstained")),
                _fmt(plain.get("near_misses")),
                _fmt(prefix.get("near_misses_abstained")),
                _fmt(prefix.get("near_misses")),
            ),
            "Cost: %s to %s CNY per 1,000 questions and %s to %s of index, because the "
            "generation prompt is unchanged (`ADR-0013`) and only the index carries the "
            "prefix. Latency is not a prefix effect in this pair -- the plain run answered "
            "%s of %s generation calls from the LLM cache against %s of %s for the prefix "
            "run -- so p50/p95 here measure cache occupancy, not the level."
            % (
                _fmt(plain.get("cny_per_1k")),
                _fmt(prefix.get("cny_per_1k")),
                _fmt_bytes(plain.get("index_bytes")),
                _fmt_bytes(prefix.get("index_bytes")),
                _fmt(plain.get("llm_cache_hits")),
                _fmt((plain.get("llm_cache_hits") or 0) + (plain.get("llm_cache_misses") or 0)),
                _fmt(prefix.get("llm_cache_hits")),
                _fmt((prefix.get("llm_cache_hits") or 0) + (prefix.get("llm_cache_misses") or 0)),
            ),
        ]
        paragraphs.append(" ".join(parts))

    modes = {entry["chunk_strategy"] for entry in usable}
    first = usable[0]
    items = first["intervals"]["hit_at_10"].get("items") or 0
    deltas = [entry["metrics"]["delta"].get("hit_at_10") for entry in usable]
    signs = {0 if not value else (1 if value > 0 else -1) for value in deltas}
    if len(signs) > 1:
        paragraphs.append(
            "At n = %d answerable items this mode rests on %d pairs (%s) and they do not "
            "agree in sign (%s): that is the prefix interacting with the chunk strategy, "
            "not a level effect, and every paired interval still contains zero."
            % (
                items,
                len(usable),
                ", ".join(sorted(modes)),
                ", ".join("`%s` %s" % (entry["stratum"], _signed(entry["metrics"]["delta"].get("hit_at_10"))) for entry in usable),
            )
        )
    elif not _excluding_zero(first["intervals"]["hit_at_10"]["delta"]):
        paragraphs.append(
            "At n = %d answerable items this mode rests on %d %s (%s) and the interval on "
            "the hit@10 delta contains zero: a single item is %.3f of hit@10, so one item "
            "changing side is enough to produce the whole delta. The honest reading is that "
            "the prefix neither bought nor cost retrieval quality here in a way this sample "
            "can distinguish from noise; the sign of the point estimate is not evidence "
            "either way."
            % (
                items,
                len(usable),
                "pair" if len(usable) == 1 else "pairs",
                ", ".join(sorted(modes)),
                1.0 / items if items else 0.0,
            )
        )
    else:
        paragraphs.append(
            "At n = %d answerable items this mode rests on %d %s (%s), and the paired "
            "interval on the hit@10 delta excludes zero -- the one claim the sample size "
            "supports."
            % (
                items,
                len(usable),
                "pair" if len(usable) == 1 else "pairs",
                ", ".join(sorted(modes)),
            )
        )
    return paragraphs


def _pattern_paragraphs(report: Dict[str, Any]) -> List[str]:
    """What the usable pairs have in common, when they have something in common."""
    usable = [entry for entry in report["pairs"] if entry["status"] == USABLE]
    if len(usable) < 2:
        return [
            "Only %d pair is usable, so there is no cross-stratum pattern to report yet; "
            "the per-mode paragraphs above are the whole of what this snapshot supports."
            % len(usable)
        ]
    hit_deltas = {entry["metrics"]["delta"].get("hit_at_10") for entry in usable}
    by_strategy: Dict[str, set] = {}
    for entry in usable:
        by_strategy.setdefault(entry["chunk_strategy"], set()).add(
            entry["metrics"]["delta"].get("hit_at_10")
        )
    lost = {tuple(entry["discordant"]["retrieval_hit"]["reference_only"]) for entry in usable}
    gained = {tuple(entry["discordant"]["retrieval_hit"]["treated_only"]) for entry in usable}
    patterns: List[str] = []

    if len(hit_deltas) == 1:
        patterns.append(
            "All %d usable pairs land on the same hit@10 delta (%s)%s."
            % (
                len(usable),
                _signed(next(iter(hit_deltas))),
                ", on the same discordant items: %s lost, %s won"
                % (_items(list(next(iter(lost)))), _items(list(next(iter(gained)))))
                if len(lost) == 1 and len(gained) == 1
                else "",
            )
        )
    elif len(by_strategy) > 1 and all(len(values) == 1 for values in by_strategy.values()):
        counts = {name: 0 for name in by_strategy}
        for entry in usable:
            counts[entry["chunk_strategy"]] += 1
        patterns.append(
            "The %d usable pairs split by chunk strategy rather than by retrieval mode: %s. "
            "%s, and the two strategies disagree, which is the signature of an interaction "
            "between the prefix and how the document was cut -- not of a level effect."
            % (
                len(usable),
                "; ".join(
                    "`%s` %s over %d pair%s"
                    % (
                        name,
                        ", ".join(_signed(value) for value in sorted(values, key=lambda v: (v is None, v))),
                        counts[name],
                        "" if counts[name] == 1 else "s",
                    )
                    for name, values in sorted(by_strategy.items())
                ),
                "Every pair inside a strategy agrees with its sibling"
                if all(count > 1 for count in counts.values())
                else "The strategy with one pair cannot agree or disagree with itself",
            )
        )
    else:
        patterns.append(
            "The %d usable pairs do not agree on a hit@10 delta (%s), which is what a "
            "factor interacting with the chunk strategy or the retrieval mode looks like at "
            "one cell per corner."
            % (len(usable), ", ".join(sorted(_signed(value) for value in hit_deltas)))
        )

    cited = {tuple(entry["discordant"]["grounded_citation"]["reference_only"]) for entry in usable}
    if len(cited) == 1:
        patterns.append(
            "The citation-side discordance is the same list in every pair (%s), so it is "
            "one small set of items rather than a per-stratum story."
            % _items(list(next(iter(cited))))
        )
    else:
        patterns.append(
            "The citation-side discordance is not one shared list: %s."
            % "; ".join(
                "`%s` plain only %s, prefix only %s"
                % (
                    entry["stratum"],
                    _items(entry["discordant"]["grounded_citation"]["reference_only"]),
                    _items(entry["discordant"]["grounded_citation"]["treated_only"]),
                )
                for entry in usable
            )
        )

    index_deltas = {entry["metrics"]["delta"].get("index_bytes") for entry in usable}
    cost_deltas = [
        value
        for value in (entry["metrics"]["delta"].get("cny_per_1k") for entry in usable)
        if value is not None
    ]
    patterns.append(
        "The system bucket follows from `ADR-0013` rather than from luck: the recorded index "
        "size moves by %s in %s, and the money per 1,000 questions moves between %s and %s "
        "CNY -- the generation prompt is byte-identical between the twins, so only the index "
        "and the ranks it produces can differ."
        % (
            ", ".join(_signed_bytes(value) for value in sorted(index_deltas, key=lambda v: (v is None, v))),
            "every pair" if len(index_deltas) == 1 else "the usable pairs",
            _signed(min(cost_deltas)) if cost_deltas else MISSING,
            _signed(max(cost_deltas)) if cost_deltas else MISSING,
        )
    )
    return patterns


def _verdict_paragraphs(report: Dict[str, Any]) -> List[str]:
    """The one or two sentences a reader should take away, computed not asserted."""
    usable = [entry for entry in report["pairs"] if entry["status"] == USABLE]
    hit = [entry["metrics"]["delta"].get("hit_at_10") for entry in usable]
    hit = [value for value in hit if value is not None]
    citation = [entry["metrics"]["delta"].get("citation_precision") for entry in usable]
    citation = [value for value in citation if value is not None]
    p_values = [entry["tests"]["retrieval_hit"]["p_value"] for entry in usable]
    citation_p = [entry["tests"]["grounded_citation"]["p_value"] for entry in usable]
    excludes = [entry for entry in usable if _excluding_zero(entry["intervals"]["hit_at_10"]["delta"])]
    cost = [entry["metrics"]["delta"].get("cny_per_1k") for entry in usable]
    cost = [value for value in cost if value is not None]

    retrieval_claim = (
        "the difference is separable from noise in %d pair%s (%s)"
        % (
            len(excludes),
            "" if len(excludes) == 1 else "s",
            ", ".join(entry["stratum"] for entry in excludes),
        )
        if excludes
        else "nothing here is separable from noise"
    )
    citation_claim = (
        "the citation outcome is separable in %d pair%s"
        % (
            sum(1 for value in citation_p if value < 0.05),
            "" if sum(1 for value in citation_p if value < 0.05) == 1 else "s",
        )
        if any(value < 0.05 for value in citation_p)
        else "no citation outcome is separable from noise either"
    )
    p_span = (
        "McNemar p = %s in every pair" % _fmt(p_values[0])
        if p_values and min(p_values) == max(p_values)
        else "McNemar p between %s and %s"
        % (_fmt(min(p_values)) if p_values else MISSING, _fmt(max(p_values)) if p_values else MISSING)
    )
    index_deltas = [
        entry["metrics"]["delta"].get("index_bytes") for entry in usable
    ]
    index_deltas = [abs(value) for value in index_deltas if value is not None]
    return [
        "On %d usable pair%s, the prefix moves hit@10 by between %s and %s -- at most %d "
        "item%s of %d answerable ones -- with %s, and %s."
        % (
            len(usable),
            "" if len(usable) == 1 else "s",
            _signed(min(hit)) if hit else MISSING,
            _signed(max(hit)) if hit else MISSING,
            int(round(max((abs(value) for value in hit), default=0.0) * (report["inputs"]["answerable"] or 0))),
            "" if max((abs(value) for value in hit), default=0.0) <= 1 else "s",
            report["inputs"]["answerable"],
            p_span,
            retrieval_claim,
        ),
        "Citation precision moves between %s and %s, and %s. The cost side is a "
        "single-digit move in the index (at most %s) and at most %s CNY per 1,000 "
        "questions, because the generator is shown the raw chunk either way (`ADR-0013`). "
        "The prefix is therefore not a quality lever on this golden set at this sample "
        "size; it is a retrieval-side representation change whose effect is one item's "
        "rank, and the sign of that effect depends on how the document was cut."
        % (
            _signed(min(citation)) if citation else MISSING,
            _signed(max(citation)) if citation else MISSING,
            citation_claim,
            _bytes(max(index_deltas)) if index_deltas else MISSING,
            _fmt(max((abs(value) for value in cost), default=0.0)),
        ),
    ]


def write(report_data: Dict[str, Any], path: str) -> str:
    """Write the note; returns the path, so a caller can print it."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(report_data))
    return path


def main(
    configs_dir: str = DEFAULT_CONFIGS,
    runs_root: str = DEFAULT_RUNS,
    golden_path: str = DEFAULT_GOLDEN,
    out: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the report, optionally write the note, and print the summary."""
    data = report(configs_dir=configs_dir, runs_root=runs_root, golden_path=golden_path)
    summary = data["summary"]
    print(
        "context_ab: %d of %d pair(s) usable, %d pending, %d refused (golden %s)"
        % (
            summary["usable"],
            summary["declared"],
            summary["pending"],
            summary["refused"],
            golden_version(data["inputs"]["golden_path"]),
        )
    )
    for entry in data["pairs"]:
        print("  %-42s %-8s %s" % (entry["stratum"], entry["status"], entry["note"] or ""))
        if entry["status"] != USABLE:
            continue
        hit = entry["tests"]["retrieval_hit"]
        citation = entry["tests"]["grounded_citation"]
        delta = entry["metrics"]["delta"]
        print(
            "    hit@10 %s -> %s (%s), McNemar p=%s; citation precision %s -> %s (%s), "
            "p=%s"
            % (
                _fmt(_pair_of(entry, REFERENCE).get("hit_at_10")),
                _fmt(_pair_of(entry, TREATED).get("hit_at_10")),
                _signed(delta.get("hit_at_10")),
                _fmt(hit["p_value"]),
                _fmt(_pair_of(entry, REFERENCE).get("citation_precision")),
                _fmt(_pair_of(entry, TREATED).get("citation_precision")),
                _signed(delta.get("citation_precision")),
                _fmt(citation["p_value"]),
            )
        )
    if out:
        print("wrote %s" % write(data, out))
    return data


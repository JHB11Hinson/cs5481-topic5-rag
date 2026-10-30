"""Tests for the contextual-prefix A/B (ticket 07, last box).

No pytest fixtures: `python -m ragqa.selftest` calls every `test_*` function with
no arguments. Each test builds its own temp tree -- a full eighteen-cell config
directory emitted by `grid.emit`, plus the run directories it wants to exist --
and removes it again. Nothing here reads or writes a real run directory.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from ragqa import config as config_mod
from ragqa import context_ab
from ragqa import grid

# ---- fixtures --------------------------------------------------------------


def _temp(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=prefix)


def _emit_configs(root: str) -> str:
    """The real eighteen-cell declaration, written under a temp directory."""
    path = os.path.join(root, "configs")
    grid.emit(path)
    return path


def _load(configs: str, cell: str):
    return config_mod.load(os.path.join(configs, cell + ".yaml"))


def _rewrite(configs: str, cell: str, key: str, value) -> None:
    """Patch one YAML line in the temp tree, so a test can pin one factor."""
    path = os.path.join(configs, cell + ".yaml")
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    old = "%s: %s" % (key, "golden/v1.jsonl")
    if old in text:
        text = text.replace(old, "%s: %s" % (key, value))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        if isinstance(payload, str):
            handle.write(payload)
        else:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")


def _write_jsonl(path: str, rows) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


GOLDEN_ROWS = [
    {
        "id": "A1",
        "answerable": True,
        "evidence": [{"doc_id": "d1", "quote": "alpha"}],
        "question": "alpha?",
    },
    {
        "id": "A2",
        "answerable": True,
        "evidence": [{"doc_id": "d1", "quote": "beta"}],
        "question": "beta?",
    },
    {
        "id": "A3",
        "answerable": True,
        "evidence": [{"doc_id": "d1", "quote": "gamma"}],
        "question": "gamma?",
    },
    {
        "id": "A4",
        "answerable": True,
        "evidence": [{"doc_id": "d1", "quote": "delta"}],
        "question": "delta?",
    },
    {"id": "N1", "answerable": False, "evidence": [], "question": "unknown one?"},
    {"id": "N2", "answerable": False, "evidence": [], "question": "unknown two?"},
]

CHUNKS = [
    {"chunk_id": "c-alpha", "doc_id": "d1", "text": "the alpha channel is set"},
    {"chunk_id": "c-beta", "doc_id": "d1", "text": "the beta channel is set"},
    {"chunk_id": "c-none", "doc_id": "d2", "text": "unrelated prose about seals"},
]


def _hit(chunk_id: str, rank: int) -> dict:
    return {"chunk_id": chunk_id, "doc_id": "d1", "rank": rank, "score": 0.9 - 0.05 * rank}


def _prediction(item_id: str, answerable: bool, retrieved, abstained: bool = False,
                claims=()) -> dict:
    return {
        "item_id": item_id,
        "answerable": answerable,
        "abstained": abstained,
        "retrieved": retrieved,
        "claims": list(claims),
        "answer_text": "",
    }


def _verdict(item_id: str, chunk_id: str, supported: bool) -> dict:
    return {
        "item_id": item_id,
        "claim_id": "%s-c1" % item_id,
        "chunk_id": chunk_id,
        "doc_id": "d1",
        "supported": supported,
        "containment_ok": supported,
        "error_class": "" if supported else "quote_not_in_chunk",
        "span_start": 4 if supported else -1,
        "span_end": 9 if supported else -1,
    }


def _metrics(hit: float, mrr: float, ndcg: float, claims: int, supported: int,
             precision: float, recall: float, span: float, over_abstain: float,
             negatives: float, cost_per_1k: float, index_bytes: int) -> dict:
    return {
        "items": {"total": len(GOLDEN_ROWS), "answerable": 4, "unanswerable": 2},
        "retrieval": {
            "k": 10,
            "hit_rate": hit,
            "recall_at_k": hit,
            "mrr": mrr,
            "ndcg_at_10": ndcg,
            "misses": [],
        },
        "citations": {
            "claims": claims,
            "supported": supported,
            "citation_precision": precision,
            "citation_recall": recall,
            "span_hit_rate": span,
            "containment_failures": {},
        },
        "abstention": {
            "abstained_answerable": 1 if over_abstain else 0,
            "over_abstain_rate": over_abstain,
            "abstained_unanswerable": int(round(negatives * 2)),
            "abstention_recall_on_negatives": negatives,
            "under_abstain": 2 - int(round(negatives * 2)),
        },
        "system": {
            "cost_cny": 0.01,
            "cost_per_1k_questions_cny": cost_per_1k,
            "index_bytes": index_bytes,
            "chunks_indexed": len(CHUNKS),
        },
    }


#: The two synthetic runs. Decided by hand, not by the code under test:
#:   plain  -- A1 hits, A2/A3/A4 miss, A4 is over-abstained, N1 is caught;
#:             two claims are made and one is supported.
#:   prefix -- A1 and A2 hit, A3/A4 miss, nothing answerable is refused, both
#:             near-misses are refused; three claims are made, two supported.
PLAIN = {
    "predictions": [
        _prediction("A1", True, [_hit("c-alpha", 1)], claims=[{"chunk_id": "c-alpha"}]),
        _prediction("A2", True, [_hit("c-none", 1)]),
        _prediction("A3", True, [_hit("c-alpha", 1)], claims=[{"chunk_id": "c-alpha"}]),
        _prediction("A4", True, [], abstained=True),
        _prediction("N1", False, [], abstained=True),
        _prediction("N2", False, []),
    ],
    "citations": [
        _verdict("A1", "c-alpha", True),
        _verdict("A3", "c-alpha", False),
    ],
    "metrics": _metrics(0.25, 0.25, 0.25, 2, 1, 0.5, 0.25, 0.5, 0.25, 0.5, 9.0, 1000),
    "timings": {"p50_ms": 10.0, "p95_ms": 20.0, "per_item_ms": [10.0] * 6},
}

PREFIX = {
    "predictions": [
        _prediction("A1", True, [_hit("c-alpha", 1)], claims=[{"chunk_id": "c-alpha"}]),
        _prediction("A2", True, [_hit("c-beta", 3)], claims=[{"chunk_id": "c-beta"}]),
        _prediction("A3", True, [_hit("c-none", 1)], claims=[{"chunk_id": "c-none"}]),
        _prediction("A4", True, [_hit("c-none", 2)]),
        _prediction("N1", False, [], abstained=True),
        _prediction("N2", False, [], abstained=True),
    ],
    "citations": [
        _verdict("A1", "c-alpha", True),
        _verdict("A2", "c-beta", True),
        _verdict("A3", "c-none", False),
    ],
    # MRR = (1 + 1/3) / 4; nDCG@10 = (1/log2(2) + 1/log2(4)) / 4.
    "metrics": _metrics(
        0.5, 0.3333, 0.375, 3, 2, round(2 / 3.0, 4), 0.5, round(2 / 3.0, 4), 0.0, 1.0, 9.5, 1005
    ),
    "timings": {"p50_ms": 30.0, "p95_ms": 40.0, "per_item_ms": [30.0] * 6},
}


def _write_run(runs_root: str, cfg, spec, stamp: str = "20260101T000000") -> str:
    """A run directory joined to its cell by the digest of its own config."""
    name = "%s-%s-%s" % (cfg["run.name"], stamp, grid.config_digest(cfg))
    path = os.path.join(runs_root, name)
    os.makedirs(path, exist_ok=True)
    _write(os.path.join(path, "config.json"), cfg.nested())
    if "metrics" in spec:
        _write(os.path.join(path, "metrics.json"), spec["metrics"])
    _write_jsonl(os.path.join(path, "predictions.jsonl"), spec["predictions"])
    _write_jsonl(os.path.join(path, "chunks.jsonl"), CHUNKS)
    _write_jsonl(os.path.join(path, "citations.jsonl"), spec.get("citations", []))
    if "timings" in spec:
        _write(os.path.join(path, "timings.json"), spec["timings"])
    return path


def _tree(configs: str, runs: str, golden: str, plain: bool = True,
          prefix: bool = True, cells=(("cell-fixed-dense-plain", "plain"),
                                     ("cell-fixed-dense-contextual_prefix", "prefix"))) -> None:
    for cell, side in cells:
        spec = PLAIN if side == "plain" else PREFIX
        if (side == "plain" and not plain) or (side == "prefix" and not prefix):
            continue
        _write_run(runs, _load(configs, cell), spec)


def _golden(root: str) -> str:
    path = os.path.join(root, "v1.jsonl")
    _write_jsonl(path, GOLDEN_ROWS)
    return path


def _pair(report, stratum: str) -> dict:
    for entry in report["pairs"]:
        if entry["stratum"] == stratum:
            return entry
    raise AssertionError("no pair for %s in %s" % (stratum, [p["stratum"] for p in report["pairs"]]))


# ---- pairing ---------------------------------------------------------------


def test_pairing_keeps_the_factors_straight() -> None:
    """Every pair is a plain cell and its contextual_prefix twin, and nothing else."""
    root = _temp("ctx-pairing-")
    try:
        configs = _emit_configs(root)
        report = context_ab.report(configs_dir=configs, runs_root=os.path.join(root, "runs"),
                                  golden_path=_golden(root))
        strata = [entry["stratum"] for entry in report["pairs"]]
        assert strata == [
            "fixed/dense",
            "fixed/hybrid",
            "fixed/rerank",
            "recursive_parent_child/dense",
            "recursive_parent_child/hybrid",
            "recursive_parent_child/rerank",
        ], strata
        for entry in report["pairs"]:
            assert set(entry["sides"]) == {context_ab.REFERENCE, context_ab.TREATED}, entry
            assert entry["sides"][context_ab.TREATED]["context_mode"] == "contextual_prefix"
            assert entry["sides"][context_ab.REFERENCE]["context_mode"] == "plain"
        assert report["summary"]["declared"] == 6
        assert report["summary"]["refused"] == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_fixed_vs_recursive_pair_is_refused() -> None:
    """One factor moved is the precondition; a chunk-strategy drift is not a pair."""
    root = _temp("ctx-drift-")
    try:
        configs = _emit_configs(root)
        # Mislabel the twin: the name stays, the resolved config changes strategy.
        source = os.path.join(configs, "cell-recursive_parent_child-dense-contextual_prefix.yaml")
        target = os.path.join(configs, "cell-fixed-dense-contextual_prefix.yaml")
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

        entry = _pair(
            context_ab.report(configs_dir=configs, runs_root=os.path.join(root, "runs"),
                              golden_path=_golden(root)),
            "fixed/dense",
        )
        assert entry["status"] == context_ab.REFUSED, entry["status"]
        assert "chunking" in entry["note"], entry["note"]
        assert entry["metrics"] == {}, "a refused pair must not carry numbers"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- the numbers -----------------------------------------------------------


def test_deltas_on_synthetic_run_directories() -> None:
    """prefix minus plain, on every bucket, from the two run directories only."""
    root = _temp("ctx-delta-")
    try:
        configs = _emit_configs(root)
        runs = os.path.join(root, "runs")
        _tree(configs, runs, _golden(root))
        report = context_ab.report(
            configs_dir=configs, runs_root=runs, golden_path=_golden(root)
        )
        entry = _pair(report, "fixed/dense")
        assert entry["status"] == context_ab.USABLE, entry["note"]

        metrics = entry["metrics"]
        plain, prefix, delta = (
            metrics[context_ab.REFERENCE],
            metrics[context_ab.TREATED],
            metrics["delta"],
        )
        assert plain["hit_at_10"] == 0.25, plain
        assert prefix["hit_at_10"] == 0.5, prefix
        assert delta["hit_at_10"] == 0.25, delta

        assert plain["mrr"] == 0.25, plain["mrr"]
        assert prefix["mrr"] == round((1.0 + 1.0 / 3.0) / 4.0, 4), prefix["mrr"]
        assert delta["ndcg_at_10"] > 0.0

        # citations: two claims one supported vs three claims two supported.
        assert plain["citation_precision"] == 0.5
        assert prefix["citation_precision"] == round(2 / 3.0, 4)
        assert delta["citation_precision"] == round(2 / 3.0 - 0.5, 4)
        assert delta["citation_recall"] == 0.25
        assert delta["span_hit_rate"] == round(2 / 3.0 - 0.5, 4)

        # abstention, counted on the 4 answerable and the 2 near-misses.
        assert plain["over_abstain_rate"] == 0.25
        assert prefix["over_abstain_rate"] == 0.0
        assert delta["over_abstain_rate"] == -0.25
        assert plain["near_misses_abstained"] == 1
        assert prefix["near_misses_abstained"] == 2
        assert delta["near_misses_abstained"] == 1
        assert prefix["near_misses"] == 2
        assert prefix["answerable"] == 4

        # system, from timings.json and metrics.json.
        assert delta["p50_ms"] == 20.0
        assert delta["p95_ms"] == 20.0
        assert delta["cny_per_1k"] == 0.5
        assert delta["index_bytes"] == 5

        # paired tests: one discordant item on each outcome, both in the prefix's favour.
        hit_test = entry["tests"]["retrieval_hit"]
        assert hit_test["pairs"] == 4
        assert hit_test["treated_only"] == 1
        assert hit_test["reference_only"] == 0
        assert hit_test["p_value"] == 1.0  # one discordant pair cannot be significant

        citation_test = entry["tests"]["grounded_citation"]
        assert citation_test["treated_only"] == 1, citation_test
        assert citation_test["reference_only"] == 0, citation_test
        assert citation_test["p_value"] == 1.0

        assert entry["drift"] == [], entry["drift"]
        assert report["summary"]["usable"] == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_missing_metrics_file_yields_pending_not_zero() -> None:
    """An unfinished twin is `pending` with a reason, never a zero delta."""
    root = _temp("ctx-pending-")
    try:
        configs = _emit_configs(root)
        runs = os.path.join(root, "runs")
        _tree(configs, runs, _golden(root), prefix=False)
        # A directory that exists but was never measured, for the hybrid stratum.
        dangling = _write_run(runs, _load(configs, "cell-fixed-hybrid-contextual_prefix"),
                              {"predictions": PREFIX["predictions"]})
        assert not os.path.isfile(os.path.join(dangling, "metrics.json"))

        report = context_ab.report(
            configs_dir=configs, runs_root=runs, golden_path=_golden(root)
        )
        dense = _pair(report, "fixed/dense")
        assert dense["status"] == context_ab.PENDING, dense["status"]
        assert "contextual_prefix" in dense["note"], dense["note"]
        assert dense["metrics"] == {}, dense["metrics"]
        assert dense["tests"] == {}, dense["tests"]

        hybrid = _pair(report, "fixed/hybrid")
        assert hybrid["status"] == context_ab.PENDING, hybrid["status"]
        assert "metrics.json" in hybrid["note"], hybrid["note"]

        absent = _pair(report, "recursive_parent_child/dense")
        assert absent["status"] == context_ab.PENDING
        assert "no run directory" in absent["note"], absent["note"]
        assert report["summary"]["usable"] == 0
        assert report["summary"]["pending"] == 6
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_twin_not_on_golden_v1_is_pending() -> None:
    """A run measured on another golden set is not the reference instrument."""
    root = _temp("ctx-golden-")
    try:
        configs = _emit_configs(root)
        _rewrite(configs, "cell-fixed-dense-contextual_prefix", "items_path", "golden/v0.jsonl")
        runs = os.path.join(root, "runs")
        _tree(configs, runs, _golden(root))
        entry = _pair(
            context_ab.report(configs_dir=configs, runs_root=runs, golden_path=_golden(root)),
            "fixed/dense",
        )
        assert entry["status"] == context_ab.PENDING, entry["status"]
        assert "golden" in entry["note"], entry["note"]
        assert entry["metrics"] == {}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_non_v1_golden_set_is_refused_up_front() -> None:
    """The note is stated on golden v1; another question set is a different claim."""
    root = _temp("ctx-golden-path-")
    try:
        configs = _emit_configs(root)
        wrong = os.path.join(root, "v0.jsonl")
        _write_jsonl(wrong, GOLDEN_ROWS)
        raised = False
        try:
            context_ab.report(
                configs_dir=configs, runs_root=os.path.join(root, "runs"), golden_path=wrong
            )
        except context_ab.ContextAbError as error:
            raised = True
            assert "golden v1" in str(error), str(error)
        assert raised, "a v0 golden set must not produce a table"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- resampling ------------------------------------------------------------


def test_seeded_bootstrap_is_reproducible() -> None:
    """Same tree, same seed, same interval -- twice, and 10,000 item resamples."""
    root = _temp("ctx-bootstrap-")
    try:
        configs = _emit_configs(root)
        runs = os.path.join(root, "runs")
        _tree(configs, runs, _golden(root))
        golden = _golden(root)
        first = _pair(context_ab.report(configs_dir=configs, runs_root=runs, golden_path=golden),
                      "fixed/dense")
        second = _pair(context_ab.report(configs_dir=configs, runs_root=runs, golden_path=golden),
                       "fixed/dense")
        one = first["intervals"]["hit_at_10"]
        two = second["intervals"]["hit_at_10"]
        assert one == two, (one, two)
        assert one["delta"]["resamples"] == 10000, one["delta"]
        assert one["delta"]["seed"] == context_ab.BOOTSTRAP_SEED
        assert one[context_ab.TREATED]["resamples"] == 10000
        # 4 answerable items, one of which flips, so the interval has to contain the point.
        assert one["delta"]["lo"] <= 0.25 <= one["delta"]["hi"], one["delta"]
        assert one["delta"]["mean"] == 0.25
        assert one["delta"]["hi"] > 0.25, one["delta"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_resample_unit_is_the_item_not_the_claim() -> None:
    """More claims on one item must not widen the interval."""
    root = _temp("ctx-unit-")
    try:
        configs = _emit_configs(root)
        runs = os.path.join(root, "runs")
        _tree(configs, runs, _golden(root))
        report = context_ab.report(
            configs_dir=configs, runs_root=runs, golden_path=_golden(root)
        )
        entry = _pair(report, "fixed/dense")
        assert entry["intervals"]["hit_at_10"][context_ab.TREATED]["n"] == 4
        assert entry["intervals"]["hit_at_10"][context_ab.TREATED]["statistic"] == "mean"
    finally:
        shutil.rmtree(root, ignore_errors=True)

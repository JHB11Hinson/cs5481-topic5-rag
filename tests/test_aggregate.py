"""Tests for the aggregate step (ticket 15).

No pytest fixtures: `python -m ragqa.selftest` calls every `test_*` function with
no arguments. Every test owns its own temp tree and removes it again.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

from ragqa import aggregate


def _temp(prefix: str) -> str:
    path = tempfile.mkdtemp(prefix=prefix)
    return path


def _metrics(
    hit: float = 0.8,
    mrr: float = 0.5,
    ndcg: float = 0.6,
    precision: float = 1.0,
    recall: float = 0.9,
    span: float = 1.0,
    over_abstain: float = 0.1,
    negatives: float = 1.0,
    cost_per_1k: float = 9.4,
    items: int = 60,
) -> dict:
    return {
        "items": {"total": items, "answerable": items - 20, "unanswerable": 20},
        "retrieval": {
            "k": 10,
            "hit_rate": hit,
            "recall_at_k": hit,
            "mrr": mrr,
            "ndcg_at_10": ndcg,
            "misses": [],
        },
        "citations": {
            "claims": 70,
            "supported": 70,
            "citation_precision": precision,
            "citation_recall": recall,
            "span_hit_rate": span,
            "containment_failures": {},
        },
        "abstention": {
            "abstained_answerable": 4,
            "over_abstain_rate": over_abstain,
            "abstained_unanswerable": 20,
            "abstention_recall_on_negatives": negatives,
            "under_abstain": 0,
        },
        "grounding": {"claims": 70, "containment_precision": precision},
        "system": {
            "cost_cny": 0.56,
            "cost_per_1k_questions_cny": cost_per_1k,
            "cost_components": {
                "generation": {"tokens_in": 422138, "tokens_out": 36175, "usd": 0.085}
            },
            "index_bytes": 23966243,
            "chunks_indexed": 2318,
            "generation_calls": items,
            "generator_model": "deepseek-v4.1-flash",
            "embedding_model": "BAAI/bge-m3",
        },
    }


def _write_run(root: str, name: str, metrics: dict, timings: dict = None) -> str:
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)
    if timings is not None:
        with open(os.path.join(path, "timings.json"), "w", encoding="utf-8") as handle:
            json.dump(timings, handle, indent=2, sort_keys=True)
    return path


def _design() -> list:
    """A three-cell design: one finished, one unfinished, one absent."""
    return [
        {
            "cell": "cell-fixed-dense-plain",
            "factors": {
                "chunk_strategy": "fixed",
                "retrieval_mode": "dense",
                "context_mode": "plain",
            },
            "run_name": "grid-fixed-dense-plain",
            "config_digest": "aaaaaaaa",
        },
        {
            "cell": "cell-fixed-hybrid-plain",
            "factors": {
                "chunk_strategy": "fixed",
                "retrieval_mode": "hybrid",
                "context_mode": "plain",
            },
            "run_name": "grid-fixed-hybrid-plain",
            "config_digest": "bbbbbbbb",
        },
        {
            "cell": "cell-fixed-rerank-plain",
            "factors": {
                "chunk_strategy": "fixed",
                "retrieval_mode": "rerank",
                "context_mode": "plain",
            },
            "run_name": "grid-fixed-rerank-plain",
            "config_digest": "cccccccc",
        },
    ]


# ---- bootstrap ------------------------------------------------------------


def test_bootstrap_ci_on_a_constant_sample_returns_that_constant() -> None:
    """Resampling a constant cannot move it: the interval collapses on the value."""
    ci = aggregate.bootstrap_mean_ci([1.0] * 20, resamples=500, seed=7)
    assert ci["mean"] == 1.0, ci
    assert ci["lo"] == 1.0, ci
    assert ci["hi"] == 1.0, ci
    assert ci["n"] == 20, ci
    assert ci["resamples"] == 500, ci
    assert ci["seed"] == 7, ci

    zero = aggregate.bootstrap_mean_ci([0.0] * 12, resamples=500, seed=7)
    assert (zero["mean"], zero["lo"], zero["hi"]) == (0.0, 0.0, 0.0), zero


def test_bootstrap_is_reproducible_under_a_fixed_seed() -> None:
    values = [0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1]
    first = aggregate.bootstrap_mean_ci(values, resamples=2000, seed=11)
    second = aggregate.bootstrap_mean_ci(values, resamples=2000, seed=11)
    other = aggregate.bootstrap_mean_ci(values, resamples=2000, seed=12)
    assert first == second, (first, second)
    assert (first["lo"], first["hi"]) != (other["lo"], other["hi"]), (first, other)
    assert first["lo"] <= first["mean"] <= first["hi"], first
    # The observed mean is the sample mean, not a resample: it must be exact.
    assert abs(first["mean"] - 7.0 / 12.0) < 1e-6, first


def test_bootstrap_ratio_ci_collapses_when_the_ratio_is_constant() -> None:
    ci = aggregate.bootstrap_ratio_ci([2, 2, 2], [2, 2, 2], resamples=400, seed=5)
    assert (ci["ratio"], ci["lo"], ci["hi"]) == (1.0, 1.0, 1.0), ci

    ci = aggregate.bootstrap_ratio_ci([1, 0, 1, 1, 1], [1, 1, 1, 1, 1], resamples=1000, seed=3)
    assert abs(ci["ratio"] - 0.8) < 1e-12, ci
    assert ci["lo"] <= ci["ratio"] <= ci["hi"], ci
    assert ci["n"] == 5, ci


# ---- McNemar --------------------------------------------------------------


def test_mcnemar_exact_matches_the_hand_computed_two_by_two() -> None:
    """b=9, c=1 -> 2 * (C(10,0) + C(10,1)) / 2**10 = 22/1024."""
    result = aggregate.mcnemar_exact(9, 1)
    assert result["b"] == 9 and result["c"] == 1, result
    assert abs(result["p_value"] - 22.0 / 1024.0) < 1e-15, result

    """b=20, c=0 -> 2 * C(20,0) / 2**20 = 2/1048576."""
    extreme = aggregate.mcnemar_exact(20, 0)
    assert abs(extreme["p_value"] - 2.0 / 1048576.0) < 1e-18, extreme

    # Symmetric in b and c: the test is two-sided.
    assert (
        aggregate.mcnemar_exact(1, 9)["p_value"] == aggregate.mcnemar_exact(9, 1)["p_value"]
    ), "McNemar is two-sided and takes the smaller discordant count"


def test_mcnemar_exact_all_agree_is_p_one() -> None:
    """No discordant pairs: nothing moved, so p = 1 rather than a divide-by-zero."""
    result = aggregate.mcnemar_exact(0, 0)
    assert result["p_value"] == 1.0, result
    assert result["b"] == 0 and result["c"] == 0, result
    assert result["pairs"] == 0, result
    assert aggregate.mcnemar_exact(0, 0)["method"] == "exact-binomial", result


def test_paired_discordance_aligns_by_item_id_and_counts_drops() -> None:
    left = {"A001": True, "A002": False, "A003": True}
    right = {"A001": True, "A002": True, "A003": False, "A004": True}
    result = aggregate.paired_discordance(left, right)
    assert result["pairs"] == 3, result
    assert result["b"] == 1, result  # A003: only the left cell is correct
    assert result["c"] == 1, result  # A002: only the right cell is correct
    assert result["unpaired_left"] == 0, result
    assert result["unpaired_right"] == 1, result


# ---- the matrix reader ----------------------------------------------------


def test_matrix_reader_marks_a_missing_cell_and_a_missing_metrics_file() -> None:
    root = _temp("agg-reader-")
    try:
        _write_run(
            root,
            "grid-fixed-dense-plain-20260101T000000-aaaaaaaa",
            _metrics(),
            {"p50_ms": 4113.52, "p95_ms": 15021.369},
        )
        # Present but not finished: a directory with no metrics.json is not a run.
        os.makedirs(os.path.join(root, "grid-fixed-hybrid-plain-20260101T000001-bbbbbbbb"))
        # cell-fixed-rerank-plain has no directory at all.

        rows = aggregate.matrix_rows(root, _design())
        assert len(rows) == 3, rows
        by_cell = {row["cell"]: row for row in rows}

        done = by_cell["cell-fixed-dense-plain"]
        assert done["status"] == "finished", done
        assert done["run_id"] == "grid-fixed-dense-plain-20260101T000000-aaaaaaaa", done
        assert done["values"]["hit_at_10"] == 0.8, done
        assert done["values"]["p50_ms"] == 4113.52, done

        half = by_cell["cell-fixed-hybrid-plain"]
        assert half["status"] == "unfinished", half
        assert half["run_id"] == "", half
        assert half["values"] == {}, half

        absent = by_cell["cell-fixed-rerank-plain"]
        assert absent["status"] == "missing", absent
        assert absent["run_id"] == "", absent
        assert absent["values"] == {}, absent
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_matrix_reader_never_invents_a_row() -> None:
    """Row count is the design's, never the run root's."""
    root = _temp("agg-invent-")
    try:
        # An orphan run that matches no cell: it must not become a row.
        _write_run(root, "real-llm-20260101T000000-6dba1b8f", _metrics())
        rows = aggregate.matrix_rows(root, _design())
        assert len(rows) == 3, rows
        assert all(row["status"] == "missing" for row in rows), rows
        assert [row["cell"] for row in rows] == [cell["cell"] for cell in _design()]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_matrix_reader_survives_a_half_written_metrics_file() -> None:
    root = _temp("agg-broken-")
    try:
        path = os.path.join(root, "grid-fixed-dense-plain-20260101T000000-aaaaaaaa")
        os.makedirs(path)
        with open(os.path.join(path, "metrics.json"), "w", encoding="utf-8") as handle:
            handle.write('{"retrieval": {"hit_rate": 0.8')
        os.makedirs(os.path.join(root, "grid-fixed-hybrid-plain-20260101T000000-bbbbbbbb"))
        rows = aggregate.matrix_rows(root, _design())
        assert len(rows) == 3, rows
        assert [row["status"] for row in rows] == ["unreadable", "unfinished", "missing"], rows
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- main effects ---------------------------------------------------------


def test_main_effects_mean_over_the_cells_that_exist_with_counts() -> None:
    root = _temp("agg-effects-")
    try:
        _write_run(
            root,
            "grid-fixed-dense-plain-20260101T000000-aaaaaaaa",
            _metrics(hit=0.8),
        )
        _write_run(
            root,
            "grid-fixed-hybrid-plain-20260101T000000-bbbbbbbb",
            _metrics(hit=0.6),
        )
        rows = aggregate.matrix_rows(root, _design())
        effects = aggregate.main_effects(rows, "retrieval_mode", "hit_at_10")
        levels = {entry["level"]: entry for entry in effects["levels"]}

        assert abs(levels["dense"]["mean"] - 0.8) < 1e-12, levels["dense"]
        assert levels["dense"]["cells"] == 1, levels["dense"]
        assert abs(levels["hybrid"]["mean"] - 0.6) < 1e-12, levels["hybrid"]
        # rerank is absent: it has no mean and no cells, and the level still prints.
        assert levels["rerank"]["mean"] is None, levels["rerank"]
        assert levels["rerank"]["cells"] == 0, levels["rerank"]
        assert effects["cells"] == 2 and effects["metric"] == "hit_at_10", effects
        # The mean of the dense level is over one cell, and the ids are named.
        assert levels["dense"]["run_ids"] == [
            "grid-fixed-dense-plain-20260101T000000-aaaaaaaa"
        ], levels["dense"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_interaction_term_is_zero_when_the_two_factors_are_additive() -> None:
    root = _temp("agg-interaction-")
    try:
        # hit = base + retrieval_effect + context_effect, exactly additive:
        # 0.5 / 0.7 / 0.6 / 0.8 -> every interaction term is zero.
        for digest, name, hit in (
            ("aaaaaaaa", "grid-fixed-dense-plain", 0.5),
            ("bbbbbbbb", "grid-fixed-hybrid-plain", 0.7),
        ):
            _write_run(root, "%s-20260101T000000-%s" % (name, digest), _metrics(hit=hit))
        design = _design()
        design.append(
            {
                "cell": "cell-fixed-dense-contextual_prefix",
                "factors": {
                    "chunk_strategy": "fixed",
                    "retrieval_mode": "dense",
                    "context_mode": "contextual_prefix",
                },
                "run_name": "grid-fixed-dense-contextual_prefix",
                "config_digest": "dddddddd",
            }
        )
        design.append(
            {
                "cell": "cell-fixed-hybrid-contextual_prefix",
                "factors": {
                    "chunk_strategy": "fixed",
                    "retrieval_mode": "hybrid",
                    "context_mode": "contextual_prefix",
                },
                "run_name": "grid-fixed-hybrid-contextual_prefix",
                "config_digest": "eeeeeeee",
            }
        )
        _write_run(
            root, "grid-fixed-dense-contextual_prefix-20260101T000000-dddddddd", _metrics(hit=0.6)
        )
        _write_run(
            root, "grid-fixed-hybrid-contextual_prefix-20260101T000000-eeeeeeee", _metrics(hit=0.8)
        )
        rows = aggregate.matrix_rows(root, design)
        table = aggregate.interaction(rows, "retrieval_mode", "context_mode", "hit_at_10")
        cells = {(entry["a"], entry["b"]): entry for entry in table["cells"]}
        # Marginals: dense 0.55, hybrid 0.75; plain 0.60, prefix 0.70; grand 0.65.
        assert abs(table["grand_mean"] - 0.65) < 1e-12, table
        # rerank/late_chunking have no finished cell: their corner is missing, not zero.
        assert cells[("rerank", "plain")]["interaction"] is None, cells[("rerank", "plain")]
        for key, entry in cells.items():
            if entry["interaction"] is None:
                assert entry["mean"] is None, (key, entry)
                continue
            assert abs(entry["interaction"]) < 1e-12, (key, entry)

        # Break additivity in one corner: hybrid/prefix 0.8 -> 0.9 deviates by 0.1 from
        # the additive prediction, which is a quarter of it in the interaction term.
        _write_run(
            root, "grid-fixed-hybrid-contextual_prefix-20260101T000000-eeeeeeee", _metrics(hit=0.9)
        )
        rows = aggregate.matrix_rows(root, design)
        table = aggregate.interaction(rows, "retrieval_mode", "context_mode", "hit_at_10")
        cells = {(entry["a"], entry["b"]): entry for entry in table["cells"]}
        assert abs(cells[("hybrid", "contextual_prefix")]["interaction"] - 0.025) < 1e-9, cells
        assert abs(cells[("dense", "plain")]["interaction"] - 0.025) < 1e-9, cells
        assert abs(cells[("dense", "contextual_prefix")]["interaction"] - (-0.025)) < 1e-9, cells
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- the whole bundle -----------------------------------------------------


def _tree(directory: str) -> dict:
    found = {}
    for base, _dirs, names in os.walk(directory):
        for name in sorted(names):
            full = os.path.join(base, name)
            relative = os.path.relpath(full, directory).replace(os.sep, "/")
            with open(full, "rb") as handle:
                found[relative] = handle.read()
    return found


def test_regeneration_from_the_same_runs_is_byte_identical() -> None:
    root = _temp("agg-runs-")
    first = _temp("agg-out-a-")
    second = _temp("agg-out-b-")
    try:
        _write_run(
            root,
            "grid-fixed-dense-plain-20260101T000000-aaaaaaaa",
            _metrics(),
            {"p50_ms": 4113.52, "p95_ms": 15021.369},
        )
        os.makedirs(os.path.join(root, "grid-fixed-hybrid-plain-20260101T000001-bbbbbbbb"))

        aggregate.regenerate(root, first, design=_design())
        aggregate.regenerate(root, second, design=_design())

        left = _tree(first)
        right = _tree(second)
        assert sorted(left) == sorted(right), (sorted(left), sorted(right))
        assert left, "the bundle is empty"
        for name in sorted(left):
            assert left[name] == right[name], "%s differs between regenerations" % name
        assert "matrix.md" in left, sorted(left)
        assert "README.md" in left, sorted(left)
        # No timestamp may enter the bundle, or two regenerations could never agree.
        text = left["matrix.md"].decode("utf-8")
        assert "generated at" not in text.lower(), text[:400]
    finally:
        for path in (root, first, second):
            shutil.rmtree(path, ignore_errors=True)

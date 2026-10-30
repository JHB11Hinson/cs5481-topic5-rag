"""Tests for the baseline comparison layer (ticket 14).

No pytest fixtures: `python -m ragqa.selftest` calls every `test_*` function with
no arguments, so each test builds the run directories it needs from the helpers
below. Expected values are hand-computed, never recomputed the way the code does.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ragqa import baselines, config as config_mod

REPO = Path(__file__).resolve().parents[1]
# The design point every baseline is declared against: recursive_parent_child /
# rerank / plain. `configs/ctx-plain.yaml` is an older, differently configured
# cell (max_tokens 900, threshold -100.0, no prefixer) and comparing against it
# would put a second factor into every row.
REFERENCE_CONFIG = (
    REPO / "configs" / "grid" / "cell-recursive_parent_child-rerank-plain.yaml"
)
BASELINE_CONFIGS = REPO / "configs" / "baselines"


# --------------------------------------------------------------------------- #
# synthetic run directories
# --------------------------------------------------------------------------- #


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def _config(run_name, **overrides):
    flat = {
        "run.name": run_name,
        "run.out_root": "runs",
        "corpus.source": "data/corpus/synthetic/docs.jsonl",
        "corpus.snapshot_id": "synthetic",
        "chunk.strategy": "recursive_parent_child",
        "embed.provider": "bge-m3",
        "embed.model_id": "BAAI/bge-m3",
        "index.backend": "qdrant",
        "retrieval.mode": "rerank",
        "retrieval.k": 10,
        "retrieval.rerank_top": 12,
        "context.mode": "plain",
        "generate.provider": "llm",
        "generate.abstain_score_threshold": -100.0,
        "golden.items_path": "golden/v1.jsonl",
        "llm.model_generate": "deepseek-v4.1-flash",
        "llm.price_in_usd_per_mtok": 0.15,
        "llm.price_out_usd_per_mtok": 0.60,
        "baseline.closed_book": False,
        "baseline.long_context": False,
        "baseline.long_context_max_chars": 12000,
    }
    flat.update(overrides)
    return config_mod._nest(flat)


def _metrics(total, answerable, misses, citation_precision, citation_recall,
             over_abstain_rate, tokens_in, tokens_out, cost_per_1k, k=10):
    return {
        "items": {
            "total": total,
            "answerable": answerable,
            "unanswerable": total - answerable,
        },
        "retrieval": {
            "k": k,
            "hit_rate": round(1.0 - len(misses) / float(answerable), 4),
            "recall_at_k": round(1.0 - len(misses) / float(answerable), 4),
            "mrr": 0.5,
            "ndcg_at_10": 0.5,
            "misses": list(misses),
        },
        "citations": {
            "claims": 0,
            "supported": 0,
            "citation_precision": citation_precision,
            "citation_recall": citation_recall,
            "span_hit_rate": 0.0,
            "containment_failures": {},
        },
        "abstention": {
            "abstained_answerable": 0,
            "over_abstain_rate": over_abstain_rate,
            "abstained_unanswerable": 0,
            "abstention_recall_on_negatives": 0.0,
            "under_abstain": 0,
        },
        "grounding": {
            "claims": 0,
            "containment_pass": 0,
            "containment_precision": citation_precision,
            "nli_judged": 0,
            "nli_pass": 0,
            "nli_precision": 0.0,
            "judge_judged": 0,
            "judge_pass": 0,
            "judge_precision": 0.0,
            "span_resolved": 0,
            "span_resolved_rate": 0.0,
        },
        "system": {
            "cost_usd": 0.001,
            "cost_cny": 0.0067,
            "cost_per_1k_questions_cny": cost_per_1k,
            "cost_components": {
                "generation": {
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "usd": 0.001,
                }
            },
            "generation_calls": total,
            "embedding_model": "BAAI/bge-m3",
            "generator_model": "deepseek-v4.1-flash",
            "closed_book": False,
            "long_context": False,
        },
    }


def _fake_run(root, run_id, cfg_name, metrics, items, timings=None):
    """`items` is a list of (item_id, answerable, abstained, n_claims, supported)."""
    path = os.path.join(root, run_id)
    _write(os.path.join(path, "config.json"), cfg_name)
    _write(os.path.join(path, "metrics.json"), metrics)
    _write(
        os.path.join(path, "timings.json"),
        timings or {"p50_ms": 100.0, "p95_ms": 200.0, "per_item_ms": [], "total_wall_seconds": 1.0},
    )
    _write_jsonl(
        os.path.join(path, "predictions.jsonl"),
        [
            {
                "item_id": item_id,
                "answerable": answerable,
                "abstained": abstained,
                "claims": [{"chunk_id": f"c-{i}"} for i in range(n_claims)],
                "retrieved": [],
                "tokens_in": 100,
                "tokens_out": 10,
            }
            for item_id, answerable, abstained, n_claims, _ in items
        ],
    )
    _write_jsonl(
        os.path.join(path, "citations.jsonl"),
        [
            {
                "item_id": item_id,
                "claim_id": f"{item_id}-c1",
                "chunk_id": f"c-{item_id}",
                "supported": supported,
                "containment_ok": supported,
                "nli_supported": None,
                "judge_supported": None,
                "error_class": "" if supported else "quote_not_in_chunk",
            }
            for item_id, _, _, n_claims, supported in items
            if n_claims
        ],
    )
    return path


def _paired_runs(root):
    """Reference supports 5 of 6 answerable items; closed book supports none.

    q6 is answered with no claim at all, which is the "answer with no citation"
    failure the table has to count separately from abstention. q4 is a retrieval
    miss that is nevertheless answered, so hit@k and citation support stay
    independent quantities.
    """
    items_reference = [
        ("q1", True, False, 1, True),
        ("q2", True, False, 1, True),
        ("q3", True, False, 1, True),
        ("q4", True, False, 1, True),
        ("q5", True, False, 1, True),
        ("q6", True, False, 0, False),
        ("u1", False, True, 0, False),
        ("u2", False, True, 0, False),
    ]
    items_closed = [(item[0], item[1], True, 0, False) for item in items_reference]

    reference = _fake_run(
        root,
        "baseline-ref-run",
        _config("baseline-ref"),
        _metrics(8, 6, ["q4"], 0.6, 0.8333, 0.0, 4000, 1000, 12.5),
        items_reference,
    )
    closed = _fake_run(
        root,
        "baseline-closed-run",
        _config("baseline-closed", **{"baseline.closed_book": True}),
        _metrics(8, 6, ["q4"], 0.0, 0.0, 1.0, 900, 400, 0.4),
        items_closed,
    )
    return reference, closed


def _flatten(tree, prefix=""):
    flat = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = value
    return flat


# --------------------------------------------------------------------------- #
# McNemar
# --------------------------------------------------------------------------- #


def test_mcnemar_exact_binomial_matches_hand_computed_table():
    # 10 discordant pairs favour the treatment, 2 favour the baseline:
    # two-sided exact p = 2 * (C(12,0) + C(12,1) + C(12,2)) / 2^12
    #                   = 2 * (1 + 12 + 66) / 4096 = 158 / 4096
    result = baselines.mcnemar_counts(10, 2)
    assert result["method"] == "exact_binomial", result
    assert result["discordant"] == 12, result
    assert result["treatment_only"] == 10 and result["baseline_only"] == 2, result
    assert abs(result["p_value"] - 158.0 / 4096.0) < 1e-12, result


def test_mcnemar_exact_branch_asymmetric_counts():
    # 1 versus 6 discordant: p = 2 * (C(7,0) + C(7,1)) / 2^7 = 2 * 8 / 128
    result = baselines.mcnemar_counts(1, 6)
    assert result["method"] == "exact_binomial", result
    assert abs(result["p_value"] - 0.125) < 1e-12, result


def test_mcnemar_with_no_discordant_pairs_is_not_significant():
    result = baselines.mcnemar_counts(0, 0)
    assert result["p_value"] == 1.0, result
    assert result["discordant"] == 0, result


def test_mcnemar_stays_exact_on_a_large_paired_sample():
    # 40 versus 10 discordant: the exact two-sided binomial tail is 2 * P(X <= 10)
    # with X ~ Binomial(50, 0.5) = 1.9e-05, which is smaller than the chi-square
    # approximation's 4.1e-05. With 60 items there is no reason to approximate.
    result = baselines.mcnemar_counts(40, 10)
    assert result["method"] == "exact_binomial", result
    assert result["discordant"] == 50, result
    assert result["p_value"] < 1e-4, result
    assert result["p_value"] > 1e-6, result
    # and it agrees with the shared implementation the matrix table uses
    from ragqa import aggregate

    assert aggregate.mcnemar_exact(40, 10)["p_value"] == result["p_value"]


def test_mcnemar_outcomes_ignores_agreeing_pairs():
    outcomes = [(True, True), (False, False), (True, False), (False, True), (True, True)]
    result = baselines.mcnemar_outcomes(outcomes)
    assert result["pairs"] == 5, result
    assert result["discordant"] == 2, result
    assert result["treatment_only"] == 1 and result["baseline_only"] == 1, result
    assert abs(result["p_value"] - 1.0) < 1e-12, result


# --------------------------------------------------------------------------- #
# config factors
# --------------------------------------------------------------------------- #


def test_every_baseline_config_loads_and_differs_from_the_reference_in_one_factor():
    """One factor each, except the MiniLM cell, which moves two.

    `retrieval.mode` is its own factor group, not part of `embedder`, so the cell
    that drops the cross-encoder *and* shrinks the embedder is reported as moving
    two factors instead of being certified as a single-variable ablation. That is
    the honest count and `notes/baselines.md` says so.
    """
    reference = config_mod.load(str(REFERENCE_CONFIG))
    paths = sorted(BASELINE_CONFIGS.glob("*.yaml"))
    assert paths, "no baseline configs found"

    expected = {
        "closed-book": ["baseline-policy"],
        "long-context": ["baseline-policy"],
        "embed-minilm": ["embedder", "retrieval-mode"],
        "gen-cheap": ["generator-model"],
    }
    seen = set()
    for path in paths:
        cfg = config_mod.load(str(path))
        seen.add(path.stem)
        diff = baselines.substantive_diff(reference, cfg)
        assert diff, f"{path.name} is identical to the reference cell"
        factors = baselines.differing_factors(diff)
        assert factors == expected[path.stem], (
            f"{path.name} varies {sorted(factors)}: {sorted(diff)}"
        )

    assert seen == set(expected), seen


def test_the_generator_swap_differs_from_the_grid_reference_in_exactly_one_factor():
    """The cell exists to move the reader, so nothing else may move with it.

    It used to carry `llm.max_tokens: 900`, `generate.abstain_score_threshold:
    -100.0` and an empty `context.prefix_model`, so against the reference cell it
    measured a budget, an abstention policy and a prefixer as well as a model.
    """
    reference = config_mod.load(str(REFERENCE_CONFIG))
    cfg = config_mod.load(str(BASELINE_CONFIGS / "gen-cheap.yaml"))
    verdict = baselines.ablation_verdict(reference, cfg)
    assert verdict["differing_factors"] == ["generator-model"], verdict
    assert verdict["ceteris_paribus"] is True, verdict
    assert cfg["llm.max_tokens"] == reference["llm.max_tokens"], cfg["llm.max_tokens"]
    assert (
        cfg["generate.abstain_score_threshold"]
        == reference["generate.abstain_score_threshold"]
    ), cfg["generate.abstain_score_threshold"]
    assert cfg["context.prefix_model"] == reference["context.prefix_model"]


def test_closed_book_and_long_context_keep_the_reference_prompt_and_generator():
    reference = config_mod.load(str(REFERENCE_CONFIG))
    closed = config_mod.load(str(BASELINE_CONFIGS / "closed-book.yaml"))
    long_context = config_mod.load(str(BASELINE_CONFIGS / "long-context.yaml"))

    assert closed["baseline.closed_book"] is True
    assert long_context["baseline.long_context"] is True
    # Closed book is the same generator and, at the config level, the same prompt:
    # nothing about generation may move, only the retrieval block that is emptied.
    for key in (
        "generate.provider",
        "generate.max_claims",
        "generate.min_claim_overlap",
        "llm.model_generate",
        "llm.temperature",
        "llm.max_tokens",
        "llm.context_chunks",
    ):
        assert closed[key] == reference[key], key
        assert long_context[key] == reference[key], key


def test_long_context_window_covers_the_longest_golden_evidence_document():
    # The cap must not handicap the cell on the items it is measured on: every
    # answerable golden item's top document is at most 19,391 chars
    # (reports/baselines/window-cost.json).
    cfg = config_mod.load(str(BASELINE_CONFIGS / "long-context.yaml"))
    assert int(cfg["baseline.long_context_max_chars"]) >= 19391
    assert int(cfg["baseline.long_context_max_chars"]) <= 24000


def test_embedding_swap_keeps_dense_retrieval_without_a_cross_encoder():
    reference = config_mod.load(str(REFERENCE_CONFIG))
    cfg = config_mod.load(str(BASELINE_CONFIGS / "embed-minilm.yaml"))
    assert cfg["embed.model_id"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg["retrieval.mode"] == "dense"
    assert cfg["retrieval.mode"] != reference["retrieval.mode"]
    # MiniLM has 256 positions and embed.py assigns max_seq_length verbatim.
    assert int(cfg["embed.max_seq_length"]) == 256


def test_generator_swap_moves_only_the_generator_and_its_price():
    reference = config_mod.load(str(REFERENCE_CONFIG))
    cfg = config_mod.load(str(BASELINE_CONFIGS / "gen-cheap.yaml"))
    assert cfg["llm.model_generate"] != reference["llm.model_generate"]
    assert cfg["llm.model_generate"] == "gpt-6-luna"
    assert float(cfg["llm.price_in_usd_per_mtok"]) == 0.10
    assert float(cfg["llm.price_out_usd_per_mtok"]) == 0.50


# --------------------------------------------------------------------------- #
# the comparison table
# --------------------------------------------------------------------------- #


def test_table_reads_two_run_directories_and_reports_the_measured_numbers():
    with tempfile.TemporaryDirectory() as root:
        reference, closed = _paired_runs(root)
        table = baselines.compare([reference, closed], reference=reference)

        rows = {row["run_id"]: row for row in table["configurations"]}
        ref = rows["baseline-ref-run"]
        cb = rows["baseline-closed-run"]

        assert ref["hit_at_k"] == 0.8333, ref["hit_at_k"]          # 5 of 6 hit
        assert ref["cny_per_1k_questions"] == 12.5, ref
        assert ref["latency_p50_ms"] == 100.0 and ref["latency_p95_ms"] == 200.0, ref
        assert ref["tokens_in"] == 4000 and ref["tokens_out"] == 1000, ref
        assert ref["tokens_total"] == 5000, ref
        assert ref["answers_with_no_citation"] == 1, ref
        assert ref["citation_support_items"] == 5, ref
        assert ref["citation_recall"] == 0.8333, ref
        assert ref["over_abstain_rate"] == 0.0, ref

        assert cb["hit_at_k"] == 0.8333, cb
        assert cb["citation_support_items"] == 0, cb
        assert cb["answers_with_no_citation"] == 0, cb
        assert cb["cny_per_1k_questions"] == 0.4, cb
        assert cb["over_abstain_rate"] == 1.0, cb
        assert cb["differing_factors_vs_reference"] == ["baseline-policy"], cb
        assert cb["ceteris_paribus"] is True, cb


def test_table_reports_paired_significance_against_the_reference():
    with tempfile.TemporaryDirectory() as root:
        reference, closed = _paired_runs(root)
        table = baselines.compare([reference, closed], reference=reference)

        comparisons = {(row["metric"], row["run_id"]): row for row in table["comparisons"]}
        citation = comparisons[("citation_support", "baseline-closed-run")]
        assert citation["baseline_only"] == 5, citation
        assert citation["treatment_only"] == 0, citation
        assert citation["method"] == "exact_binomial", citation
        # 5 of 5 discordant pairs all against the baseline: 2 / 2^5 = 0.0625
        assert abs(citation["p_value"] - 0.0625) < 1e-12, citation

        retrieval = comparisons[("retrieval_hit", "baseline-closed-run")]
        assert retrieval["discordant"] == 0, retrieval
        assert retrieval["p_value"] == 1.0, retrieval


def test_table_writes_markdown_and_json():
    with tempfile.TemporaryDirectory() as root:
        reference, closed = _paired_runs(root)
        out = os.path.join(root, "reports")
        written = baselines.report([reference, closed], out, reference=reference)

        assert written["json"].endswith("table.json"), written
        assert written["markdown"].endswith("table.md"), written
        payload = json.load(open(written["json"], encoding="utf-8"))
        assert payload["reference_run_id"] == "baseline-ref-run", payload
        assert len(payload["configurations"]) == 2, payload
        text = open(written["markdown"], encoding="utf-8").read()
        assert "baseline-closed-run" in text, text
        assert "McNemar" in text, text


def test_table_flags_two_runs_that_differ_in_more_than_one_factor():
    with tempfile.TemporaryDirectory() as root:
        reference, closed = _paired_runs(root)
        os.remove(os.path.join(closed, "config.json"))
        _write(
            os.path.join(closed, "config.json"),
            _config(
                "baseline-closed",
                **{"baseline.closed_book": True, "llm.model_generate": "mimo-v2.6-flash"},
            ),
        )
        table = baselines.compare([reference, closed], reference=reference)
        row = [r for r in table["configurations"] if r["run_id"] == "baseline-closed-run"][0]
        assert sorted(row["differing_factors_vs_reference"]) == [
            "baseline-policy",
            "generator-model",
        ], row
        assert row["ceteris_paribus"] is False, row


def test_compare_needs_at_least_two_runs():
    with tempfile.TemporaryDirectory() as root:
        reference, _ = _paired_runs(root)
        try:
            baselines.compare([reference])
        except ValueError as error:
            assert "two" in str(error).lower(), error
        else:
            raise AssertionError("compare accepted a single run directory")


def test_reference_cell_derivation_moves_only_identity_keys():
    from scripts.run_baselines import reference_config

    base = config_mod.load(str(REFERENCE_CONFIG))
    derived = reference_config("golden/v1.jsonl")
    assert derived["golden.items_path"] == "golden/v1.jsonl"
    assert derived["run.name"] == "baseline-reference"
    # Everything substantive must be untouched, or the headline comparison would
    # have a second factor in it.
    assert baselines.substantive_diff(base, derived) == {}


# --------------------------------------------------------------------------- #
# the runner
# --------------------------------------------------------------------------- #


def test_dry_run_prints_the_cells_and_calls_no_model():
    with tempfile.TemporaryDirectory() as out:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "run_baselines.py"),
                "--dry-run",
                "--out",
                out,
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        output = proc.stdout + proc.stderr
        assert proc.returncode == 0, output
        assert "dry-run" in output.lower(), output
        for stem in ("closed-book", "long-context", "embed-minilm", "gen-cheap"):
            assert stem in output, output
        assert "Projected generation calls" in output, output
        assert os.listdir(out) == [], os.listdir(out)


def test_dry_run_refuses_to_call_a_model_even_when_a_key_is_present():
    with tempfile.TemporaryDirectory() as out:
        env = dict(os.environ)
        env["LLM_API_KEY"] = "sk-placeholder-not-used"
        env["LLM_BASE_URL"] = "http://127.0.0.1:9/v1"  # unroutable on purpose
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "run_baselines.py"),
                "--dry-run",
                "--out",
                out,
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
        )
        output = proc.stdout + proc.stderr
        assert proc.returncode == 0, output
        assert os.listdir(out) == [], os.listdir(out)


def _full_config(run_name, **overrides):
    values = dict(config_mod.DEFAULTS)
    values.update(_flatten(_config(run_name, **overrides)))
    return config_mod.Config(values)


def test_resume_skips_a_cell_that_already_has_a_metrics_file():
    with tempfile.TemporaryDirectory() as out:
        root = os.path.join(out, "runs")
        reference, closed = _paired_runs(root)
        full = _full_config("baseline-closed", **{"baseline.closed_book": True})
        other = _full_config("baseline-ref")
        # A real run directory records the whole resolved configuration, so both
        # have to be written out in full before resume can recognise them.
        _write(os.path.join(closed, "config.json"), full.nested())
        _write(os.path.join(reference, "config.json"), other.nested())

        found = baselines.completed_run(root, full)
        assert found == closed, found
        # The reference cell's own configuration must not be mistaken for it.
        assert baselines.completed_run(root, other) == reference


def test_resume_does_not_adopt_a_run_whose_config_is_only_a_subset():
    """A stale or partial directory must not be credited to a cell.

    Matching on the keys the two configurations happen to share credited any older
    run of the same family whose config.json had since lost a key -- which is
    exactly what a partially written directory looks like.
    """
    with tempfile.TemporaryDirectory() as out:
        root = os.path.join(out, "runs")
        _reference, closed = _paired_runs(root)
        full = _full_config("baseline-closed", **{"baseline.closed_book": True})

        # _fake_run writes the partial tree: fewer keys than the resolved config.
        assert baselines.completed_run(root, full) is None
        # Add one more key but keep the set incomplete: still not the same run.
        partial = _flatten(_config("baseline-closed", **{"baseline.closed_book": True}))
        partial["llm.model_generate"] = "deepseek-v4.1-flash"
        _write(os.path.join(closed, "config.json"), config_mod.Config(partial).nested())
        assert baselines.completed_run(root, full) is None
        # Only the whole configuration matching is enough.
        _write(os.path.join(closed, "config.json"), full.nested())
        assert baselines.completed_run(root, full) == closed


# --------------------------------------------------------------------------- #
# the window measurement
# --------------------------------------------------------------------------- #


def test_window_measurement_counts_truncation_and_corpus_shape():
    from scripts.run_baselines import measure_window

    with tempfile.TemporaryDirectory() as root:
        corpus_path = os.path.join(root, "docs.jsonl")
        _write_jsonl(
            corpus_path,
            [
                {"doc_id": "doc/short", "text": "x" * 400},
                {"doc_id": "doc/long", "text": "y" * 900},
            ],
        )
        golden_path = os.path.join(root, "items.jsonl")
        _write_jsonl(
            golden_path,
            [
                {"id": "q1", "question": "how long?", "answerable": True},
                {"id": "q2", "question": "how short?", "answerable": True},
            ],
        )
        run_dir = os.path.join(root, "run")
        _write(
            os.path.join(run_dir, "config.json"),
            {
                "corpus": {"source": corpus_path, "snapshot_id": "synthetic"},
                "golden": {"items_path": golden_path},
                "llm": {
                    "context_chunks": 1,
                    "price_in_usd_per_mtok": 0.15,
                    "price_out_usd_per_mtok": 0.60,
                },
            },
        )
        _write_jsonl(
            os.path.join(run_dir, "chunks.jsonl"),
            [
                {"chunk_id": "c-1", "doc_id": "doc/short", "kind": "child", "text": "x" * 400},
                {"chunk_id": "c-2", "doc_id": "doc/long", "kind": "child", "text": "y" * 400},
            ],
        )
        _write_jsonl(
            os.path.join(run_dir, "predictions.jsonl"),
            [
                {"item_id": "q1", "answerable": True, "tokens_in": 100, "tokens_out": 10,
                 "retrieved": [{"chunk_id": "c-1", "doc_id": "doc/short", "rank": 1}]},
                {"item_id": "q2", "answerable": True, "tokens_in": 100, "tokens_out": 10,
                 "retrieved": [{"chunk_id": "c-2", "doc_id": "doc/long", "rank": 1}]},
            ],
        )
        out_path = os.path.join(root, "window.json")
        summary = measure_window(run_dir, out_path, caps=(500, 1000))

        assert summary["items"] == 2 and summary["answerable"] == 2, summary["items"]
        assert summary["corpus"]["documents"] == 2, summary["corpus"]
        assert summary["corpus"]["total_chars"] == 1300, summary["corpus"]
        assert summary["corpus"]["max"] == 900, summary["corpus"]
        # 400 chars is inside a 500 cap, 900 is not; both fit inside 1000.
        assert summary["shapes"]["long_context_500"]["items_full"] == 1, summary["shapes"]
        assert summary["shapes"]["long_context_500"]["items_truncated"] == 1, summary["shapes"]
        assert summary["shapes"]["long_context_1000"]["items_full"] == 2, summary["shapes"]
        # A window inside the cap must cost less prompt than one over it.
        assert (
            summary["shapes"]["long_context_500"]["prompt_tokens_mean"]
            < summary["shapes"]["long_context_1000"]["prompt_tokens_mean"]
        ), summary["shapes"]
        # No model is reachable from here: both token counts were measured at 100.
        assert summary["measured_tokens_in_mean"] == 100.0, summary
        assert os.path.exists(out_path)


def test_retrieval_mode_is_its_own_factor_group():
    """Dropping the cross-encoder is a different decision from swapping the embedder."""
    assert baselines.differing_factors(["retrieval.mode"]) == ["retrieval-mode"]
    assert baselines.differing_factors(["embed.model_id"]) == ["embedder"]


def test_an_identical_pair_is_reported_as_identical_not_as_one_factor():
    """`len(factors) <= 1` certified two copies of a cell as a valid ablation."""
    cfg = config_mod.load(str(REFERENCE_CONFIG))
    same = config_mod.load(str(REFERENCE_CONFIG))
    verdict = baselines.ablation_verdict(cfg, same)
    assert verdict["factor_count"] == 0, verdict
    assert verdict["ceteris_paribus"] is False, verdict
    assert verdict["ablation_verdict"] == "IDENTICAL", verdict

    distinct = baselines.ablation_verdict(
        cfg, config_mod.load(str(BASELINE_CONFIGS / "gen-cheap.yaml"))
    )
    assert distinct["ablation_verdict"] == "ONE_FACTOR", distinct
    assert distinct["factor_count"] == 1, distinct

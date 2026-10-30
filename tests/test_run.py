from __future__ import annotations

import json
import os
import tempfile

from ragqa import config as config_mod
from ragqa import run as run_mod
from ragqa.contract import PARTIAL_SUFFIX, RunContract

# --------------------------------------------------------------------------- #
# (a) cost: every component prices its output tokens at the output price
# --------------------------------------------------------------------------- #

PRICE_IN = 0.15
PRICE_OUT = 0.60


def test_output_tokens_are_priced_at_the_output_price():
    """One million in and one million out costs price_in + price_out, not 2*price_in."""
    components = run_mod.cost_components(
        {"tokens_in": 1_000_000, "tokens_out": 1_000_000}, PRICE_IN, PRICE_OUT
    )
    assert components["generation"]["usd"] == 0.75


def test_prefix_and_rewrite_components_price_their_output_tokens():
    """The published warm-up figure, repriced: 336,389 in and 36,405 out.

    Under the old pricing this was 0.055919 USD / CNY 0.37298, which charged the
    prefix's 36,405 completion tokens at the input rate.
    """
    components = run_mod.cost_components(
        {"tokens_in": 0, "tokens_out": 0},
        PRICE_IN,
        PRICE_OUT,
        prefix={"tokens_in": 336_389, "tokens_out": 36_405},
        rewrite={"tokens_in": 1_000_000, "tokens_out": 1_000_000},
    )
    assert round(components["prefix"]["usd"], 6) == 0.072301
    assert round(components["prefix"]["usd"] * 6.67, 5) == 0.48225
    assert components["rewrite"]["usd"] == 0.75


def test_an_unset_judge_price_falls_back_to_the_generation_rate():
    components = run_mod.cost_components(
        {"tokens_in": 0, "tokens_out": 0},
        PRICE_IN,
        PRICE_OUT,
        judge={"tokens_in": 1_000_000, "tokens_out": 1_000_000},
        judge_price_in=0.0,
        judge_price_out=0.0,
    )
    assert components["judge"]["usd"] == 0.75


def test_absent_components_are_absent_not_zero():
    components = run_mod.cost_components({"tokens_in": 10, "tokens_out": 20}, PRICE_IN, PRICE_OUT)
    assert sorted(components) == ["generation"]


# --------------------------------------------------------------------------- #
# (b) long-context: one synthetic hit, handed to the prompt and the verifier
# --------------------------------------------------------------------------- #


def _cfg(**overrides):
    values = dict(config_mod.DEFAULTS)
    values.update(
        {
            "corpus.source": "fixtures/smoke/docs.jsonl",
            "corpus.snapshot_id": "fixture-smoke-v1",
            "golden.items_path": "fixtures/smoke/golden.jsonl",
        }
    )
    values.update(overrides)
    return config_mod.Config(values)


DOCUMENT = {
    "doc_id": "docs/secrets/databases/mysql-maria",
    "text": "MySQL is one of the supported plugins. " * 100,
}


def _retrieved():
    return [
        {
            "chunk_id": "chunk-42",
            "doc_id": DOCUMENT["doc_id"],
            "rank": 1,
            "score": 0.91,
            "text": "MySQL is one of the supported plugins.",
        }
    ]


def test_long_context_hands_the_prompt_and_the_verifier_the_same_hit():
    served = run_mod.item_context(
        _cfg(**{"baseline.long_context": True, "baseline.long_context_max_chars": 120}),
        _retrieved(),
        {DOCUMENT["doc_id"]: DOCUMENT},
    )
    assert served["verify_hits"] is served["prompt_hits"]
    assert len(served["prompt_hits"]) == 1
    hit = served["prompt_hits"][0]
    assert hit["synthetic"] is True
    assert hit["rank"] == 1
    assert hit["doc_id"] == DOCUMENT["doc_id"]
    assert hit["text"] == DOCUMENT["text"][:120]
    # A synthetic hit names a document, never a chunk id a chunker could have made.
    assert hit["chunk_id"] not in {row["chunk_id"] for row in _retrieved()}


def test_closed_book_hands_an_empty_context_to_both_sides():
    served = run_mod.item_context(
        _cfg(**{"baseline.closed_book": True}), _retrieved(), {DOCUMENT["doc_id"]: DOCUMENT}
    )
    assert served["prompt_hits"] == [] and served["verify_hits"] == []


def test_a_normal_run_verifies_against_the_retrieved_chunks():
    retrieved = _retrieved()
    served = run_mod.item_context(_cfg(), retrieved, {DOCUMENT["doc_id"]: DOCUMENT})
    assert served["prompt_hits"] is retrieved and served["verify_hits"] is retrieved


# --------------------------------------------------------------------------- #
# (c) ADR-0003: a run is published only once metrics.json exists
# --------------------------------------------------------------------------- #


def test_a_partial_contract_writes_into_a_suffixed_directory_and_renames():
    root = tempfile.mkdtemp(prefix="ragqa-runs-")
    contract = RunContract(root, "run-abc", partial=True)
    assert os.path.basename(str(contract.path)) == "run-abc" + PARTIAL_SUFFIX
    contract.write_json("config.json", {"a": 1})
    assert not os.path.isdir(os.path.join(root, "run-abc"))

    final = contract.finalize()
    assert os.path.basename(str(final)) == "run-abc"
    assert os.path.isfile(os.path.join(root, "run-abc", "config.json"))
    assert not os.path.isdir(os.path.join(root, "run-abc" + PARTIAL_SUFFIX))


def test_a_failed_run_leaves_no_directory_and_no_partial():
    root = tempfile.mkdtemp(prefix="ragqa-runs-")
    original = run_mod._execute

    def boom(cfg, contract, run_id):
        contract.write_json("config.json", {"a": 1})
        raise RuntimeError("the process died mid-run")

    run_mod._execute = boom
    try:
        run_mod.execute(_cfg(**{"run.name": "unit"}), root)
    except RuntimeError:
        pass
    else:
        raise AssertionError("a failing run was reported as success")
    finally:
        run_mod._execute = original

    assert os.listdir(root) == [], os.listdir(root)


def test_a_killed_runs_partial_directory_is_swept_before_the_next_run():
    root = tempfile.mkdtemp(prefix="ragqa-runs-")
    leftover = os.path.join(root, "dead-run-20260101T000000-deadbeef" + PARTIAL_SUFFIX)
    os.makedirs(leftover)
    with open(os.path.join(leftover, "config.json"), "w", encoding="utf-8") as handle:
        json.dump({"run": {"name": "dead-run"}}, handle)

    original = run_mod._execute

    def fake(cfg, contract, run_id):
        contract.write_json("metrics.json", {"ok": True})
        return {"run_id": run_id, "run_dir": str(contract.path), "metrics": {}, "missing": []}

    run_mod._execute = fake
    try:
        result = run_mod.execute(_cfg(**{"run.name": "unit"}), root)
    finally:
        run_mod._execute = original

    assert not os.path.isdir(leftover)
    assert os.path.isfile(os.path.join(result["run_dir"], "metrics.json"))
    assert not result["run_dir"].endswith(PARTIAL_SUFFIX)
    assert sorted(os.listdir(root)) == [os.path.basename(result["run_dir"])]

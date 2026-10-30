"""Tests for answer correctness and the chunking comparison (ticket 18).

No pytest fixtures: `python -m ragqa.selftest` calls every `test_*` function with
no arguments, so each test builds the run directory, the plan or the chunk set it
needs from the helpers below. Expected values are hand-computed, never recomputed
the way the code does.

The two requirements under test are brief item 5 ("report retrieval hit rate and
answer correctness") and brief item 1 ("compare at least two chunking strategies
and report their impact on retrieval quality"), neither of which had a number
before this ticket (notes/report-factcheck.md §2 rows 11 and 17).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from ragqa import correctness

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _write_json(path, payload):
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


class _Client:
    """The smallest stand-in for `LLMClient.complete` that a judge accepts."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.last_stats = {"hits": 0, "misses": 0, "tokens_in": 0, "tokens_out": 0}

    def complete(self, model, messages, max_tokens=800, json_mode=True, **_ignored):
        self.prompts.append(messages)
        text = self.replies.pop(0) if self.replies else ""
        return {
            "text": text,
            "tokens_in": 1000,
            "tokens_out": 20,
            "latency_ms": 1.0,
            "cached": False,
        }


def _fail(message):
    raise AssertionError(message)


# --------------------------------------------------------------------------- #
# the judge prompt
# --------------------------------------------------------------------------- #


def test_judge_prompt_carries_question_reference_and_generated_answer():
    messages = correctness.build_messages(
        "How many threads should merges use?",
        "16 threads.",
        "Merges use 16 threads.",
    )
    if [m["role"] for m in messages] != ["system", "user"]:
        _fail(f"expected a system and a user message, got {[m['role'] for m in messages]}")
    text = "\n".join(m["content"] for m in messages)
    for required in (
        "How many threads should merges use?",
        "16 threads.",
        "Merges use 16 threads.",
    ):
        if required not in text:
            _fail(f"judge prompt omits {required!r}; the judge cannot grade what it cannot see")
    # The gateway rejects `response_format: json_object` unless the prompt says
    # "json", so the contract has to be spelled out in the system message.
    if "json" not in messages[0]["content"].lower():
        _fail("system message must ask for json: the gateway rejects json_object without it")


# --------------------------------------------------------------------------- #
# the judge verdict
# --------------------------------------------------------------------------- #


def test_a_fenced_reply_parses_and_garbage_is_a_parse_failure():
    parsed = correctness.parse_reply('```json\n{"correct": true, "reason": "same fact"}\n```')
    if parsed != {"correct": True, "reason": "same fact"}:
        _fail(f"a fenced json reply must parse, got {parsed!r}")
    # Anything that is not a verdict is None, not `{"correct": false}`: an
    # unparseable reply must not be silently scored as a wrong answer.
    for junk in (
        "The answer looks right to me.",
        "```\n\n```",
        '{"reason": "no verdict key at all"}',
        '{"correct": "maybe"}',
    ):
        if correctness.parse_reply(junk) is not None:
            _fail(f"{junk!r} must not parse as a verdict")


def test_a_garbage_reply_is_marked_a_parse_failure_rather_than_incorrect():
    judge = correctness.CorrectnessJudge(_Client(["I would say this one is fine."]), model="m")
    verdict = judge.judge("q?", "the reference", "the generated answer")
    if verdict["correct"] is not None:
        _fail("a parse failure must not be reported as correct or incorrect")
    if verdict["parse_failure"] is not True:
        _fail("the verdict has to say the reply was unparseable")
    if judge.stats["calls"] != 1 or judge.stats["parse_failures"] != 1:
        _fail(f"stats must count the failure separately, got {judge.stats}")


def test_the_judge_reports_the_verdict_its_reply_states():
    judge = correctness.CorrectnessJudge(
        _Client(['{"correct": false, "reason": "the reference says 16, this says 32"}']),
        model="m",
    )
    verdict = judge.judge("How many threads?", "16 threads.", "32 threads.")
    if verdict["correct"] is not False:
        _fail(f"expected incorrect, got {verdict}")
    if "16" not in verdict["reason"]:
        _fail("the judge's one-sentence reason has to survive the parser")


# --------------------------------------------------------------------------- #
# the three numbers
# --------------------------------------------------------------------------- #


def _verdict(item_id, correct, abstained=False):
    return {
        "item_id": item_id,
        "answerable": True,
        "abstained": abstained,
        "judged": not abstained,
        "correct": False if abstained else correct,
        "reason": "abstained" if abstained else "judged",
        "parse_failure": False,
    }


def test_an_abstention_counts_against_all_items_and_leaves_the_answered_rate():
    verdicts = (
        [_verdict(f"A{i:03d}", correct=False, abstained=True) for i in range(1, 5)]
        + [_verdict(f"A{i:03d}", correct=True) for i in range(5, 9)]
        + [_verdict(f"A{i:03d}", correct=False) for i in range(9, 11)]
    )
    score = correctness.score_items(verdicts)
    if score["answerable"] != 10 or score["answered"] != 6 or score["abstentions"] != 4:
        _fail(f"expected 10 answerable, 6 answered, 4 abstentions; got {score}")
    if score["correct"] != 4:
        _fail(f"expected 4 correct answers, got {score['correct']}")
    # Same numerator, deliberately different denominators: the first metric is
    # what a user asking every question experiences, the second is the accuracy
    # of the generator when it commits to an answer.
    if round(score["accuracy_all"], 4) != 0.4:
        _fail(f"accuracy over all 10 answerable items must be 0.4, got {score['accuracy_all']}")
    if round(score["accuracy_answered"], 4) != 0.6667:
        _fail(f"accuracy over the 6 answered items must be 0.6667, got {score['accuracy_answered']}")
    if score["accuracy_all"] is score["accuracy_answered"]:
        _fail("the two accuracies must stay separate numbers, not one folded value")


def test_a_parse_failure_is_counted_separately_and_never_counts_as_correct():
    verdicts = [_verdict("A001", correct=True), _verdict("A002", correct=False)]
    verdicts[1].update({"correct": None, "parse_failure": True})
    score = correctness.score_items(verdicts)
    if score["parse_failures"] != 1:
        _fail(f"the unparseable verdict must be counted, got {score}")
    if score["correct"] != 1 or round(score["accuracy_all"], 4) != 0.5:
        _fail(f"an unknown verdict is not a correct one, got {score}")


def test_an_abstention_is_never_sent_to_the_judge():
    run_dir = tempfile.mkdtemp(prefix="correctness-run-")
    _write_jsonl(
        os.path.join(run_dir, "predictions.jsonl"),
        [
            {"item_id": "A001", "answerable": True, "abstained": False,
             "answer_text": "It starts in a sealed state."},
            {"item_id": "A002", "answerable": True, "abstained": True,
             "answer_text": "The documentation does not cover this."},
            {"item_id": "U001", "answerable": False, "abstained": True,
             "answer_text": "No such thing is documented."},
        ],
    )
    golden = {
        "A001": {"answerable": True, "reference_answer": "It starts in a sealed state."},
        "A002": {"answerable": True, "reference_answer": "It accepts 128 characters."},
        "U001": {"answerable": False, "reference_answer": ""},
    }
    client = _Client(['{"correct": true, "reason": "identical"}'])
    judge = correctness.CorrectnessJudge(client, model="m")
    verdicts = correctness.judge_run(run_dir, golden, judge)
    if len(client.prompts) != 1:
        _fail(f"only the one answered item should be judged, {len(client.prompts)} calls made")
    by_id = {v["item_id"]: v for v in verdicts}
    if set(by_id) != {"A001", "A002"}:
        _fail(f"only answerable items get a verdict, got {sorted(by_id)}")
    if by_id["A002"]["correct"] is not False or by_id["A002"]["judged"] is not False:
        _fail(f"an abstention on an answerable item is not correct and is not judged: {by_id['A002']}")
    if by_id["A001"]["correct"] is not True:
        _fail(f"the answered item's verdict must come from the judge: {by_id['A001']}")


# --------------------------------------------------------------------------- #
# interval, price, emitters
# --------------------------------------------------------------------------- #


def test_the_bootstrap_interval_is_seeded_and_reproducible():
    values = [1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 0, 1] * 2
    first = correctness.bootstrap_interval(values, seed=11)
    again = correctness.bootstrap_interval(values, seed=11)
    if first != again:
        _fail("the same seed must reproduce the same interval, or no number is re-runnable")
    if not first["lo"] <= first["mean"] <= first["hi"]:
        _fail(f"the interval must contain the mean: {first}")
    # A 0/1 vector resamples onto the lattice k/40, so its percentile bounds are
    # lattice points whatever the seed. The interval has to be honest about that
    # rather than spend the seed's freedom on a value the data cannot produce.
    for bound in (first["lo"], first["hi"]):
        if abs(bound * 40 - round(bound * 40)) > 1e-6:
            _fail(f"a 0/1 resample mean lands on a multiple of 1/40, got {bound}")

    # The seed has to reach the resampler. A continuous vector shows it, because
    # its resample means do not collapse onto a lattice.
    graded = [round(0.1 * ((i * 7) % 11), 3) for i in range(41)]
    bounds = {
        (
            correctness.bootstrap_interval(graded, seed=seed)["lo"],
            correctness.bootstrap_interval(graded, seed=seed)["hi"],
        )
        for seed in range(11, 21)
    }
    if len(bounds) < 2:
        _fail("ten seeds all produced the same interval, so the seed is being ignored")

    if correctness.cell_seed("cell-fixed-dense-plain") != correctness.cell_seed(
        "cell-fixed-dense-plain"
    ):
        _fail("a cell's seed has to be stable across runs")
    if correctness.cell_seed("cell-fixed-dense-plain") == correctness.cell_seed(
        "cell-fixed-hybrid-plain"
    ):
        _fail("two cells must not share a seed, or their intervals move together")


def test_the_judge_price_falls_back_to_the_generation_price():
    prices = correctness.judge_prices(
        {
            "llm.price_judge_in_usd_per_mtok": 0.0,
            "llm.price_judge_out_usd_per_mtok": 0.0,
            "llm.price_in_usd_per_mtok": 0.15,
            "llm.price_out_usd_per_mtok": 0.6,
        }
    )
    if prices != {"in": 0.15, "out": 0.6}:
        _fail(f"an unset judge price falls back to the generator's, got {prices}")
    set_prices = correctness.judge_prices(
        {
            "llm.price_judge_in_usd_per_mtok": 2.0,
            "llm.price_judge_out_usd_per_mtok": 8.0,
            "llm.price_in_usd_per_mtok": 0.15,
            "llm.price_out_usd_per_mtok": 0.6,
        }
    )
    if set_prices != {"in": 2.0, "out": 8.0}:
        _fail(f"a set judge price wins over the fallback, got {set_prices}")


def test_cost_arithmetic_uses_the_price_table():
    cost = correctness.judge_cost(1_000_000, 1_000_000, {"in": 0.15, "out": 0.6})
    if round(cost["usd"], 6) != 0.75:
        _fail(f"1M in at 0.15 plus 1M out at 0.60 is $0.75, got {cost['usd']}")
    if round(cost["cny"], 6) != round(0.75 * 6.67, 6):
        _fail(f"CNY must use the 6.67 rate the rest of the report uses, got {cost['cny']}")
    empty = correctness.judge_cost(0, 0, {"in": 0.15, "out": 0.6})
    if empty["usd"] != 0.0:
        _fail("no tokens is no money")


def _finished_row(cell="cell-fixed-dense-plain"):
    return {
        "cell": cell,
        "run_id": "grid-fixed-dense-plain-20261030T124637-8ae4eb06",
        "status": "finished",
        "chunk_strategy": "fixed",
        "retrieval_mode": "dense",
        "context_mode": "plain",
        "answerable": 40,
        "answered": 38,
        "abstentions": 2,
        "correct": 30,
        "parse_failures": 0,
        "accuracy_all": 0.75,
        "accuracy_all_lo": 0.6,
        "accuracy_all_hi": 0.875,
        "accuracy_answered": 0.7895,
        "accuracy_answered_lo": 0.6316,
        "accuracy_answered_hi": 0.9167,
        "judge_calls": 38,
        "tokens_in": 19000,
        "tokens_out": 900,
        "cost_usd": 0.0034,
        "cost_cny": 0.0227,
    }


def _pending_row(cell="cell-fixed-hybrid-late_chunking"):
    row = {field: None for field in correctness.ROW_FIELDS}
    row.update({"cell": cell, "run_id": "", "status": "pending"})
    return row


def test_the_csv_emitter_prints_a_pending_row_as_empty_cells_not_zeros():
    text = correctness.render_csv([_finished_row(), _pending_row()])
    lines = text.strip().splitlines()
    if lines[0].split(",")[:3] != ["cell", "run_id", "status"]:
        _fail(f"the header has to name the join keys first, got {lines[0]!r}")
    if len(lines) != 3:
        _fail(f"one row per cell, header aside: got {len(lines)} lines")
    if "pending" not in lines[2]:
        _fail("a cell with no run must say pending")
    if ",0.0," in lines[2] or lines[2].count(",0,"):
        _fail(f"a pending cell is not a zero, it is a blank: {lines[2]!r}")
    if "0.75" not in lines[1] or "0.7895" not in lines[1]:
        _fail("both accuracies belong in the row, not one blended number")


def test_the_markdown_emitter_states_the_three_numbers_and_how_to_regenerate():
    payload = {
        "runs_root": "D:\\path\\to\\runs",
        "protocol": {
            "judge_model": "deepseek-v4-pro",
            "bootstrap_resamples": 10000,
            "bootstrap_seed": 20261030,
        },
        "totals": {"finished": 1, "pending": 1, "judge_calls": 38, "cost_cny": 0.0227},
        "cells": [_finished_row(), _pending_row()],
    }
    text = correctness.render_markdown(payload)
    for required in (
        "cell-fixed-dense-plain",
        "cell-fixed-hybrid-late_chunking",
        "pending",
        "0.7500",
        "0.7895",
        "deepseek-v4-pro",
        "python scripts/score_correctness.py",
    ):
        if required not in text:
            _fail(f"the note must carry {required!r}")


def test_a_cell_row_carries_both_intervals_and_the_call_count():
    verdicts = [
        _verdict("A001", correct=True),
        _verdict("A002", correct=True),
        _verdict("A003", correct=False),
        _verdict("A004", correct=False, abstained=True),
    ]
    stats = {"calls": 3, "tokens_in": 3000, "tokens_out": 60, "cache_hits": 0, "cache_misses": 3}
    row = correctness.cell_row(
        cell="cell-fixed-dense-plain",
        run_id="run-a",
        factors={"chunk_strategy": "fixed", "retrieval_mode": "dense", "context_mode": "plain"},
        verdicts=verdicts,
        judge_stats=stats,
        prices={"in": 0.15, "out": 0.6},
    )
    if row["status"] != "finished" or row["run_id"] != "run-a":
        _fail(f"a finished cell names its run: {row}")
    if row["accuracy_all"] != 0.5 or row["accuracy_answered"] != round(2 / 3, 4):
        _fail(f"the row's accuracies are wrong: {row['accuracy_all']} / {row['accuracy_answered']}")
    if row["judge_calls"] != 3 or row["abstentions"] != 1:
        _fail(f"three judged calls and one abstention: {row['judge_calls']} / {row['abstentions']}")
    if row["accuracy_all_lo"] is None or row["accuracy_all_hi"] is None:
        _fail("each accuracy needs its own bootstrap interval")
    expected_cny = round((3000 / 1e6 * 0.15 + 60 / 1e6 * 0.6) * 6.67, 6)
    if row["cost_cny"] != expected_cny:
        _fail(f"cost must follow the tokens and the price table: {row['cost_cny']} != {expected_cny}")
    if set(row) != set(correctness.ROW_FIELDS):
        _fail(f"the row must fill exactly ROW_FIELDS, got {sorted(row)}")


# --------------------------------------------------------------------------- #
# the chunking comparison
# --------------------------------------------------------------------------- #

sys.path.insert(0, str(REPO))
from scripts import chunk_comparison  # noqa: E402  (needs REPO on the path)


def _cell(name, strategy, retrieval, context, run_dir="", status="finished"):
    return {
        "cell": name,
        "factors": {
            "chunk_strategy": strategy,
            "retrieval_mode": retrieval,
            "context_mode": context,
        },
        "run_dir": run_dir,
        "status": status,
    }


def test_chunk_pairing_refuses_a_pair_that_differs_in_more_than_the_strategy():
    fixed = _cell("cell-fixed-hybrid-plain", "fixed", "hybrid", "plain", "runs/fixed")
    crossed = _cell(
        "cell-recursive_parent_child-dense-plain", "recursive_parent_child", "dense", "plain",
        "runs/other",
    )
    try:
        chunk_comparison.validate_pair(fixed, crossed)
    except ValueError as error:
        if "retrieval" not in str(error):
            _fail(f"the refusal must name the factor that moved, got {error}")
    else:
        _fail("pairing a hybrid cell with a dense cell compares two things at once")

    same_strategy = _cell("cell-fixed-dense-plain", "fixed", "dense", "plain", "runs/second")
    try:
        chunk_comparison.validate_pair(fixed, same_strategy)
    except ValueError:
        pass
    else:
        _fail("two fixed cells are not a chunking comparison")

    chunk_comparison.validate_pair(
        fixed, _cell("cell-recursive_parent_child-hybrid-plain", "recursive_parent_child",
                     "hybrid", "plain", "runs/recursive")
    )


def test_a_cell_whose_twin_has_not_finished_is_pending_not_zero():
    cells = [
        _cell("cell-fixed-dense-plain", "fixed", "dense", "plain", "runs/fixed", "finished"),
        _cell("cell-recursive_parent_child-dense-plain", "recursive_parent_child", "dense",
              "plain", "", "pending"),
        _cell("cell-fixed-hybrid-plain", "fixed", "hybrid", "plain", "runs/fixed-h", "finished"),
        _cell("cell-recursive_parent_child-hybrid-plain", "recursive_parent_child", "hybrid",
              "plain", "runs/rec-h", "finished"),
    ]
    pairs = chunk_comparison.pair_cells(cells)
    if len(pairs) != 2:
        _fail(f"two (retrieval, context) keys were declared, got {len(pairs)} pairs")
    by_mode = {pair["retrieval_mode"]: pair for pair in pairs}
    dense, hybrid = by_mode["dense"], by_mode["hybrid"]
    if dense["status"] != "pending":
        _fail(f"a pair with one finished side must be pending, got {dense['status']}")
    if dense["missing"] != ["recursive_parent_child"]:
        _fail(f"the pending pair must name the side that is missing, got {dense['missing']}")
    if "comparison" in dense:
        _fail("a pending pair must carry no numbers at all")
    if hybrid["status"] != "finished" or hybrid["missing"]:
        _fail(f"a pair with both sides finished is finished: {hybrid}")


def test_a_comparison_row_reports_the_delta_in_the_expected_direction():
    fixed = {
        "retrieval": {"hit_rate": 0.8, "mrr": 0.4, "ndcg_at_10": 0.5},
        "citations": {"citation_precision": 0.9, "citation_recall": 0.8, "span_hit_rate": 0.9},
        "abstention": {"abstained_answerable": 4, "over_abstain_rate": 0.1},
    }
    recursive = {
        "retrieval": {"hit_rate": 0.9, "mrr": 0.45, "ndcg_at_10": 0.55},
        "citations": {"citation_precision": 0.95, "citation_recall": 0.85, "span_hit_rate": 0.91},
        "abstention": {"abstained_answerable": 2, "over_abstain_rate": 0.05},
    }
    row = chunk_comparison.delta_row("dense", "plain", fixed, recursive)
    if round(row["hit_at_10"]["delta"], 4) != 0.1:
        _fail(f"recursive 0.9 less fixed 0.8 is +0.1, got {row['hit_at_10']}")
    if round(row["citation_precision"]["delta"], 4) != 0.05:
        _fail(f"citation precision moves +0.05, got {row['citation_precision']}")
    if row["abstentions"]["delta"] != -2:
        _fail(f"two fewer abstentions is a negative delta, got {row['abstentions']}")
    if row["mrr"]["fixed"] != 0.4 or row["mrr"]["recursive"] != 0.45:
        _fail("both sides belong in the row, not only the difference")


def test_the_over_budget_composition_says_what_the_budget_bought():
    root = tempfile.mkdtemp(prefix="chunks-")
    set_dir = os.path.join(root, "snap-recursive_parent_child-512-p1024")
    os.makedirs(set_dir, exist_ok=True)
    rows = [
        # over budget because a table row cannot be split
        {"chunk_id": "c1", "kind": "child", "token_count": 700,
         "text": "| Method | Path |\n| :--- | :--- |\n| `GET` | `/sys/health` |"},
        # over budget because a code fence cannot be split
        {"chunk_id": "c2", "kind": "child", "token_count": 640,
         "text": "```\nvault operator init\n```"},
        # over budget for no structural reason: plain prose
        {"chunk_id": "c3", "kind": "child", "token_count": 600, "text": "Long prose. More prose. "},
        # inside budget
        {"chunk_id": "c4", "kind": "child", "token_count": 100, "text": "Short."},
        {"chunk_id": "c5", "kind": "parent", "token_count": 1024, "text": "Parent text."},
    ]
    _write_jsonl(os.path.join(set_dir, "chunks.jsonl"), rows)
    _write_json(
        os.path.join(set_dir, "chunk_stats.json"),
        {
            "chunk_set_id": os.path.basename(set_dir),
            "strategy": "recursive_parent_child",
            "chunks": 4,
            "parents": 1,
            "mean_tokens": 510.0,
            "p95_tokens": 700,
            "share_containing_table_row": 0.25,
            "share_containing_code_fence": 0.25,
            "share_ending_mid_sentence": 0.0,
            "share_over_budget": 0.75,
        },
    )
    mechanism = chunk_comparison.chunk_mechanism(set_dir, budget=512)
    if mechanism["chunks"] != 4 or mechanism["parents"] != 1:
        _fail(f"child and parent counts come from the set: {mechanism}")
    if mechanism["over_budget"] != 3:
        _fail(f"three of the four children exceed the 512 budget, got {mechanism['over_budget']}")
    if mechanism["over_budget_with_table"] != 1 or mechanism["over_budget_with_fence"] != 1:
        _fail(f"one over-budget child is a table and one a fence: {mechanism}")
    if round(mechanism["over_budget_structural_share"], 4) != round(2 / 3, 4):
        _fail(
            "two of the three over-budget children are over because of a table or a fence; "
            f"got {mechanism['over_budget_structural_share']}"
        )
    if mechanism["source"] != "chunk_set":
        _fail(f"the recomputed numbers must say where they came from: {mechanism['source']}")

"""Score answer correctness for every finished configuration (ticket 18).

    python scripts/score_correctness.py \
        --runs-root "D:/DE Project/wt/exp/runs" \
        --report-json reports/correctness.json \
        --report-csv reports/correctness.csv \
        --note notes/correctness.md

One judge call per *answered* answerable item, cached by content hash, so the
first pass costs money and every later pass is free and byte-identical. Nothing
is written into a run directory: the run root is read-only input here, the way it
is for `ragqa.aggregate`.

The three numbers per configuration are computed in `ragqa.correctness` and kept
apart — accuracy over all answerable items, accuracy over the answered ones, and
the abstention count — because folding them into one figure would hide the
trade-off the abstention threshold moves.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ragqa import config as config_mod, correctness, grid  # noqa: E402

DEFAULT_JUDGE = "deepseek-v4-pro"
DEFAULT_CACHE = "data/cache/llm.correctness.sqlite"


def load_golden(path: str) -> Dict[str, Dict[str, Any]]:
    """Golden items by id, including the question the judge needs.

    `aggregate.load_golden` keeps the evidence quotes and the reference answer for
    a retrieval audit; a correctness verdict also needs the question itself, so
    this reads the same file for the same fields plus that one.
    """
    from ragqa.corpus import read_jsonl

    golden: Dict[str, Dict[str, Any]] = {}
    for row in read_jsonl(path):
        golden[row["id"]] = {
            "answerable": bool(row.get("answerable")),
            "question": row.get("question", ""),
            "reference_answer": row.get("reference_answer", ""),
            "type": row.get("type", ""),
        }
    return golden


def cell_records(runs_root: str, configs_dir: str = "") -> List[Dict[str, Any]]:
    """The declared configurations, each with its finished run directory if any."""
    paths = [configs_dir] if configs_dir else None
    return [
        {
            "cell": cell["cell"],
            "factors": cell["factors"],
            "status": cell["status"],
            "run_dir": cell["run_dir"],
            "config_path": cell["config_path"],
            "items": cell["items"],
        }
        for cell in grid.plan(paths, out_root=runs_root)
    ]


def prices_from(config_path: str) -> Dict[str, float]:
    """The judge's USD-per-Mtok price, read from the cell that produced the runs."""
    try:
        cfg = config_mod.load(config_path).as_dict()
    except Exception:  # noqa: BLE001 - an unreadable cell must not stop the scoring
        return {"in": 0.0, "out": 0.0}
    return correctness.judge_prices(cfg)


def excluded_runs(
    runs_root: str, claimed: Sequence[str], golden: Dict[str, Any], golden_path: str
) -> List[Dict[str, Any]]:
    """Finished run directories that are not one of the declared configurations.

    Smoke configurations and the golden-v0 probes share the run root with the
    matrix. They are listed with the reason they are not in the table rather than
    scored against a Golden QA Set they were never run on.
    """
    claimed_set = {os.path.abspath(path) for path in claimed if path}
    answerable = {item for item, entry in golden.items() if entry.get("answerable")}
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(runs_root):
        return rows
    for name in sorted(os.listdir(runs_root)):
        path = os.path.join(runs_root, name)
        if not os.path.isdir(path) or os.path.abspath(path) in claimed_set:
            continue
        predictions = os.path.join(path, "predictions.jsonl")
        if not os.path.isfile(predictions) or not os.path.isfile(os.path.join(path, "metrics.json")):
            continue
        items_path = ""
        try:
            with open(os.path.join(path, "config.json"), "r", encoding="utf-8") as handle:
                items_path = str(((json.load(handle).get("golden") or {}).get("items_path")) or "")
        except (OSError, ValueError):
            items_path = ""
        ids = set()
        with open(predictions, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    ids.add(json.loads(line).get("item_id", ""))
        overlap = len(ids & answerable)
        if items_path and items_path != golden_path:
            reason = "ran `%s`, not the Golden QA Set this table scores (`%s`)" % (
                items_path,
                golden_path,
            )
        elif overlap == len(answerable):
            reason = "matches the Golden QA Set but is not a declared configuration"
        else:
            reason = "subset of the Golden QA Set: %d of %d answerable items" % (
                overlap,
                len(answerable),
            )
        rows.append({"run_id": name, "answerable_items_covered": overlap, "reason": reason})
    return rows


def _stats_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, int]:
    """One configuration's share of the campaign's calls, tokens and cache traffic."""
    return {
        key: int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0)
        for key in ("calls", "correct", "parse_failures", "tokens_in", "tokens_out",
                    "cache_hits", "cache_misses")
    }


def score_cells(
    cells: Sequence[Dict[str, Any]],
    golden: Dict[str, Dict[str, Any]],
    judge: correctness.CorrectnessJudge,
    prices: Dict[str, float],
    max_cells: Optional[int] = None,
) -> tuple:
    """Rows for every cell, plus the per-item verdicts behind them."""
    rows: List[Dict[str, Any]] = []
    verdicts: Dict[str, List[Dict[str, Any]]] = {}
    done = 0
    for cell in cells:
        if cell["status"] != "finished" or not cell["run_dir"]:
            rows.append(correctness.pending_row(cell["cell"], cell["factors"]))
            continue
        if max_cells is not None and done >= int(max_cells):
            rows.append(correctness.pending_row(cell["cell"], cell["factors"]))
            continue
        began = time.perf_counter()
        before = dict(judge.stats)
        item_verdicts = correctness.judge_run(cell["run_dir"], golden, judge)
        score = correctness.score_items(item_verdicts)
        row = correctness.cell_row(
            cell=cell["cell"],
            run_id=os.path.basename(cell["run_dir"]),
            factors=cell["factors"],
            verdicts=item_verdicts,
            # The judge's counters are cumulative over the campaign; a row owes its
            # own calls, tokens and spend, not the total so far.
            judge_stats=_stats_delta(before, judge.stats),
            prices=prices,
        )
        rows.append(row)
        verdicts[row["run_id"]] = item_verdicts
        done += 1
        print(
            "  %-46s answers %2d/%2d  answered %2d/%2d  abstain %d  calls %2d  %.1fs"
            % (
                cell["cell"],
                score["correct"],
                score["answerable"],
                score["answered"],
                score["answerable"],
                score["abstentions"],
                row["judge_calls"],
                time.perf_counter() - began,
            )
        )
    return rows, verdicts


def build_payload(
    runs_root: str,
    golden_path: str,
    rows: Sequence[Dict[str, Any]],
    verdicts: Dict[str, List[Dict[str, Any]]],
    judge: correctness.CorrectnessJudge,
    prices: Dict[str, float],
    excluded: Sequence[Dict[str, Any]],
    cache_path: str,
) -> Dict[str, Any]:
    finished = [row for row in rows if row.get("status") == "finished"]
    campaign = correctness.judge_cost(judge.stats["tokens_in"], judge.stats["tokens_out"], prices)
    return {
        "runs_root": runs_root,
        "golden_path": golden_path,
        "protocol": {
            "judge_model": judge.model_id,
            "judge_prompt": "question + reference answer + generated answer, one verdict per item",
            "judge_reasoning_effort": "none",
            "price_in": prices["in"],
            "price_out": prices["out"],
            "price_unit": "USD per million tokens",
            "usd_to_cny": correctness.USD_TO_CNY,
            "cache_path": cache_path,
            "bootstrap_resamples": correctness.BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": correctness.BOOTSTRAP_SEED,
            "bootstrap_confidence": correctness.BOOTSTRAP_CONFIDENCE,
            "resample_unit": "item",
            "abstention_semantics": (
                "an abstention on an answerable item is not correct for accuracy_all and is "
                "excluded from accuracy_answered; it is never sent to the judge"
            ),
        },
        "totals": {
            "finished": len(finished),
            "pending": len(rows) - len(finished),
            "judge_calls": int(judge.stats["calls"]),
            "tokens_in": int(judge.stats["tokens_in"]),
            "tokens_out": int(judge.stats["tokens_out"]),
            "cache_hits": int(judge.stats["cache_hits"]),
            "cache_misses": int(judge.stats["cache_misses"]),
            "parse_failures": int(judge.stats["parse_failures"]),
            "cost_usd": campaign["usd"],
            "cost_cny": campaign["cny"],
        },
        "cells": list(rows),
        "verdicts": {run: list(items) for run, items in verdicts.items()},
        "excluded_runs": list(excluded),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="score_correctness", description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--golden", default="golden/v1.jsonl")
    parser.add_argument("--configs", default="")
    parser.add_argument("--report-json", default="reports/correctness.json")
    parser.add_argument("--report-csv", default="reports/correctness.csv")
    parser.add_argument("--note", default="notes/correctness.md")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE)
    parser.add_argument("--cache-path", default=DEFAULT_CACHE)
    parser.add_argument("--max-cells", type=int, default=None)
    parser.add_argument("--cells", default="", help="comma-separated cell name substrings")
    args = parser.parse_args(argv)

    golden = load_golden(args.golden)
    if not golden:
        raise SystemExit("no golden items at %s" % args.golden)
    cells = cell_records(args.runs_root, args.configs)
    if args.cells:
        wanted = [part.strip() for part in args.cells.split(",") if part.strip()]
        cells = [cell for cell in cells if any(part in cell["cell"] for part in wanted)]

    prices = prices_from(cells[0]["config_path"]) if cells else {"in": 0.0, "out": 0.0}

    from ragqa.llm import LLMClient

    client = LLMClient(
        cache_path=args.cache_path,
        session_header="x-opencode-session",
        # A verdict is mechanical work: the thinking channel costs 10-20x the
        # output tokens and can return empty content inside a small budget.
        reasoning_effort="none",
    )
    judge = correctness.CorrectnessJudge(client, model=args.judge_model)
    try:
        print(
            "%d declared configuration(s), golden %s, judge %s"
            % (len(cells), args.golden, args.judge_model)
        )
        rows, verdicts = score_cells(cells, golden, judge, prices, max_cells=args.max_cells)
    finally:
        client.close()

    excluded = excluded_runs(
        args.runs_root, [cell["run_dir"] for cell in cells], golden, args.golden
    )
    payload = build_payload(
        args.runs_root, args.golden, rows, verdicts, judge, prices, excluded, args.cache_path
    )

    for path in (args.report_json, args.report_csv, args.note):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
    with open(args.report_json, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(args.report_csv, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(correctness.render_csv(rows))
    with open(args.note, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(correctness.render_markdown(payload))

    finished = payload["totals"]["finished"]
    print(
        "\n%d finished, %d pending; %d judge calls (%d cached), CNY %.4f"
        % (
            finished,
            payload["totals"]["pending"],
            payload["totals"]["judge_calls"],
            payload["totals"]["cache_hits"],
            payload["totals"]["cost_cny"],
        )
    )
    for row in rows:
        if row["status"] != "finished":
            continue
        print(
            "%-46s all %.4f [%.4f, %.4f]  answered %.4f [%.4f, %.4f]  abstain %d"
            % (
                row["cell"],
                row["accuracy_all"],
                row["accuracy_all_lo"],
                row["accuracy_all_hi"],
                row["accuracy_answered"],
                row["accuracy_answered_lo"],
                row["accuracy_answered_hi"],
                row["abstentions"],
            )
        )
    print("wrote %s, %s, %s" % (args.report_json, args.report_csv, args.note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

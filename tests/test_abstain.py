"""Abstention sweep: grid, rates, working point, artifacts.

The seams under test are the module's public surface:
`THRESHOLD_GRID`, `Item`, `fit_transform`, `curve`, `choose_working_point`,
`load_items`, `mode_for_run` and `sweep_command`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ragqa import abstain

# --- fixtures -------------------------------------------------------------


def _write_run(root, run_name, rows, threshold=0.0):
    """One run directory: predictions.jsonl plus the config.json a run writes."""
    path = Path(root) / run_name
    path.mkdir(parents=True, exist_ok=True)
    with (path / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    (path / "config.json").write_text(
        json.dumps(
            {
                "retrieval": {"mode": "dense", "k": 10},
                "generate": {"abstain_score_threshold": threshold},
                "run": {"name": run_name},
            }
        ),
        encoding="utf-8",
    )
    return path


def _row(item_id, answerable, score, chunks=3):
    """One prediction row; `score` is the top score, the rest decay below it."""
    retrieved = [
        {
            "chunk_id": f"c-{item_id}-{rank}",
            "doc_id": f"docs/demo/{item_id}",
            "rank": rank,
            "score": round(score - 0.01 * (rank - 1), 6),
        }
        for rank in range(1, chunks + 1)
    ]
    return {
        "item_id": item_id,
        "answerable": answerable,
        "abstained": False,
        "abstain_reason": "",
        "claims": [],
        "citation_chunk_ids": [],
        "retrieved": retrieved,
    }


def _items(pairs):
    """Items from (item_id, answerable, score) triples, identity scale."""
    return [
        abstain.Item(
            item_id=item_id,
            answerable=answerable,
            top_score=score,
            retrieved=(),
            run_id="synthetic",
        )
        for item_id, answerable, score in pairs
    ]


def _separable_run(root, run_name, positive=0.98, negative=0.02, count=5):
    rows = [_row(f"P{i}", True, positive - 0.001 * i) for i in range(count)]
    rows += [_row(f"N{i}", False, negative + 0.001 * i) for i in range(count)]
    return _write_run(root, run_name, rows)


# --- grid -----------------------------------------------------------------


def test_threshold_grid_is_eighteen_points_spanning_the_documented_interval():
    grid = abstain.THRESHOLD_GRID
    assert len(grid) == 18
    assert grid[0] == 0.2
    assert grid[-1] == 0.9
    steps = [round(b - a, 6) for a, b in zip(grid, grid[1:])]
    assert all(step > 0 for step in steps)
    # The ticket fixes both the interval and the point count; 18 points across
    # [0.2, 0.9] cannot be a 0.05 step (that would be 15 points), so the module
    # spends the step on resolution instead: ~0.0412, finer than 0.05.
    assert all(0.04 < step < 0.05 for step in steps)


# --- rates ----------------------------------------------------------------


def test_curve_reports_over_and_under_abstain_separately():
    items = _items(
        [
            ("A1", True, 0.95),
            ("A2", True, 0.85),
            ("A3", True, 0.50),
            ("A4", True, 0.10),
            ("N1", False, 0.60),
            ("N2", False, 0.05),
        ]
    )
    (point,) = abstain.curve(items, abstain.IDENTITY, grid=(0.50,))

    # 3 of 4 answerable items clear 0.50; 1 of 2 near-misses wrongly clears it.
    assert point["t"] == 0.50
    assert point["precision"] == 0.75
    assert point["recall"] == 0.75
    assert point["over_abstain_rate_on_answerable"] == 0.25
    assert point["under_abstain_rate_on_near_miss"] == 0.50


def test_curve_threshold_is_inclusive_on_the_score():
    items = _items([("A1", True, 0.50), ("N1", False, 0.50)])
    (point,) = abstain.curve(items, abstain.IDENTITY, grid=(0.50,))
    # generate.py abstains when score < threshold, so score == threshold answers.
    assert point["recall"] == 1.0
    assert point["under_abstain_rate_on_near_miss"] == 1.0


def test_curve_emits_one_row_per_grid_point():
    items = _items([("A1", True, 0.70), ("N1", False, 0.30)])
    points = abstain.curve(items, abstain.IDENTITY)
    assert len(points) == 18
    assert [p["t"] for p in points] == list(abstain.THRESHOLD_GRID)


# --- working point --------------------------------------------------------


def test_working_point_lands_on_the_boundary_when_positives_and_negatives_separate():
    items = _items([(f"P{i}", True, 0.97 - 0.01 * i) for i in range(5)])
    items += _items([(f"N{i}", False, 0.03 + 0.01 * i) for i in range(5)])

    chosen = abstain.choose_working_point(abstain.curve(items, abstain.IDENTITY))

    assert chosen["constraint_feasible"] is True
    assert chosen["t"] == abstain.THRESHOLD_GRID[-1]
    assert chosen["over_abstain_rate_on_answerable"] == 0.0
    assert chosen["under_abstain_rate_on_near_miss"] == 0.0
    assert chosen["f1"] == 1.0


def test_working_point_buys_recall_with_precision_when_scores_overlap():
    # A4 sits below the grid floor, so no threshold answers every answerable item:
    # the budget is infeasible and the rule falls back to the smallest
    # over-abstention rate, which is reached by stepping down to the last t that
    # still clears A3 — strictly inside the grid, not at an edge.
    items = _items(
        [
            ("A1", True, 0.90),
            ("A2", True, 0.80),
            ("A3", True, 0.40),
            ("A4", True, 0.10),
            ("N1", False, 0.85),
            ("N2", False, 0.60),
            ("N3", False, 0.05),
            ("N4", False, 0.02),
        ]
    )
    points = abstain.curve(items, abstain.IDENTITY)
    chosen = abstain.choose_working_point(points)

    assert chosen["constraint_feasible"] is False  # no t answers all answerable
    assert chosen["over_abstain_rate_on_answerable"] == min(
        p["over_abstain_rate_on_answerable"] for p in points
    )
    assert chosen["f1"] == max(p["f1"] for p in points)
    assert chosen["t"] not in (abstain.THRESHOLD_GRID[0], abstain.THRESHOLD_GRID[-1])


# --- scale transform ------------------------------------------------------


def test_zscore_transform_inverts_and_puts_its_midpoint_on_the_run_mean():
    transform = abstain.fit_transform([0.0, 1.0, 2.0, 3.0, 4.0], "zscore-normal-cdf")

    assert transform.kind == "zscore-normal-cdf"
    assert round(transform.mean, 6) == 2.0
    # t = 0.5 is the median of the fitted normal, i.e. the run's own mean: a
    # property of the definition, not of this implementation.
    assert round(transform.inverse(0.5), 6) == 2.0
    assert transform.forward(2.0) == 0.5
    assert transform.inverse(0.0001) < transform.inverse(0.9999)
    for target in (0.2, 0.55, 0.9):
        assert abs(transform.forward(transform.inverse(target)) - target) < 1e-9


def test_degenerate_score_distribution_is_refused_not_faked():
    try:
        abstain.fit_transform([0.031, 0.031, 0.031], "zscore-normal-cdf")
    except abstain.AbstainError as error:
        assert "no spread" in str(error) or "spread" in str(error)
    else:
        raise AssertionError("a constant score column must not produce a transform")


def test_raw_threshold_column_is_the_raw_scale_equivalent_of_t():
    items = _items([(f"P{i}", True, 10.0 + i) for i in range(4)])
    items += _items([(f"N{i}", False, 1.0 + i) for i in range(4)])
    transform = abstain.fit_transform([item.top_score for item in items], "zscore-normal-cdf")

    points = abstain.curve(items, transform)
    for point in points:
        assert abs(transform.forward(point["raw_threshold"]) - point["t"]) < 1e-6
    assert points[0]["raw_threshold"] < points[-1]["raw_threshold"]


# --- loading runs ---------------------------------------------------------


def test_mode_is_read_from_the_run_name(tmp_path=None):
    assert abstain.mode_for_run("real-hybrid-20261030T092148-08d22872") == "hybrid"
    assert abstain.mode_for_run("real-rerank-20261030T095541-a6eb2d5e") == "rerank"
    assert abstain.mode_for_run("real-llm-20261030T113604-a5c0a3e4") == "llm"
    assert abstain.mode_for_run("smoke-20261030T085149-9d616d8d") is None


def test_load_items_recovers_top_score_and_label(tmp_path=None):
    root = Path(_tmp())
    run = _separable_run(root, "real-dense-20260101T000000-abcdef12", count=3)
    items = abstain.load_items(run)

    assert len(items) == 6
    first = min(items, key=lambda item: item.item_id)
    assert first.item_id == "N0"
    assert first.answerable is False
    assert first.top_score == 0.02
    assert abstain.load_items(run)[0].run_id == run.name


def test_missing_score_column_raises_a_clear_error(tmp_path=None):
    root = Path(_tmp())
    row = _row("A1", True, 0.9)
    del row["retrieved"][0]["score"]
    run = _write_run(root, "real-dense-20260101T000000-abcdef12", [row])

    try:
        abstain.load_items(run)
    except abstain.AbstainError as error:
        message = str(error)
        assert run.name in message
        assert "A1" in message
        assert "score" in message
    else:
        raise AssertionError("a score-less row must raise instead of faking a curve")


def test_empty_retrieval_raises_a_clear_error(tmp_path=None):
    root = Path(_tmp())
    row = _row("A1", True, 0.9)
    row["retrieved"] = []
    run = _write_run(root, "real-dense-20260101T000000-abcdef12", [row])

    try:
        abstain.load_items(run)
    except abstain.AbstainError as error:
        assert "A1" in str(error)
    else:
        raise AssertionError("an item with no candidates has no score to sweep")


def test_newest_run_wins_when_a_mode_has_several(tmp_path=None):
    root = Path(_tmp())
    _write_run(root, "real-dense-20260101T000000-aaaaaaaa", [_row("A1", True, 0.30)])
    _write_run(root, "real-dense-20260102T000000-bbbbbbbb", [_row("A1", True, 0.80)])

    groups = abstain.discover_runs(root)
    items = abstain.collect_mode_items(groups["dense"])

    assert len(items) == 1
    assert items[0].top_score == 0.80
    assert items[0].run_id == "real-dense-20260102T000000-bbbbbbbb"


# --- end to end -----------------------------------------------------------


def test_sweep_command_writes_csv_png_and_working_points():
    root = Path(_tmp())
    _separable_run(root, "real-dense-20260101T000000-aaaaaaaa")
    out = root / "reports"

    code = abstain.sweep_command(root, out)

    assert code == 0
    directory = out / "abstention"
    csv_path = directory / "dense-pr.csv"
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == (
        "t,precision,recall,over_abstain_rate_on_answerable,"
        "under_abstain_rate_on_near_miss,raw_threshold"
    )
    assert len(lines) == 1 + 18

    png_path = directory / "dense-pr.png"
    assert png_path.exists() and png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    payload = json.loads((directory / "working-points.json").read_text(encoding="utf-8"))
    assert payload["modes"]["dense"]["t"] == 0.9
    assert payload["modes"]["dense"]["justification"]

    examples = (directory / "near-miss-examples.md").read_text(encoding="utf-8")
    sections = [line for line in examples.splitlines() if line.startswith("### N")]
    assert len(sections) >= 3
    assert all("ABSTAINED — correct" in line for line in sections)
    # The top chunk of the hardest near-miss is shown by id, so a reader can find
    # the passage that almost answered an unanswerable question.
    assert "`c-N4-1`" in examples


def test_sweep_command_reports_an_unreadable_run_instead_of_a_curve():
    root = Path(_tmp())
    row = _row("A1", True, 0.9)
    del row["retrieved"][0]["score"]
    _write_run(root, "real-dense-20260101T000000-aaaaaaaa", [row])

    assert abstain.sweep_command(root, root / "reports") == 2


def test_sweep_command_refuses_a_modes_request_with_no_runs():
    root = Path(_tmp())
    _separable_run(root, "real-dense-20260101T000000-aaaaaaaa")
    assert abstain.sweep_command(root, root / "reports", modes=["hybrid"]) == 2


# --- helpers --------------------------------------------------------------


_TMP_STATE = {}


def _tmp():
    """A fresh directory per test call; selftest runs test functions with no args."""
    import tempfile
    import itertools

    _TMP_STATE.setdefault("root", tempfile.mkdtemp(prefix="abstain-test-"))
    _TMP_STATE["counter"] = _TMP_STATE.get("counter", itertools.count())
    return Path(_TMP_STATE["root"]) / f"case-{next(_TMP_STATE['counter'])}"

def test_mode_is_recovered_from_the_run_config_when_the_name_says_nothing():
    """A grid cell called `cell-fixed-rerank-plain` still has a readable scale."""
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="ragqa-mode-"))
    run = root / "cell-fixed-rerank-plain-20261101T000000-abcd1234"
    run.mkdir(parents=True)
    (run / "config.json").write_text(
        json.dumps(
            {
                "retrieval": {"mode": "rerank", "k": 10},
                "generate": {"provider": "llm"},
            }
        ),
        encoding="utf-8",
    )
    assert abstain.mode_for_run(run.name) is None
    assert abstain.mode_from_config(run) == "llm"

    (run / "config.json").write_text(
        json.dumps({"retrieval": {"mode": "hybrid"}, "generate": {"provider": "llm"}}),
        encoding="utf-8",
    )
    assert abstain.mode_from_config(run) == "hybrid"

    (run / "config.json").write_text(
        json.dumps({"retrieval": {"mode": "dense"}, "generate": {"provider": "llm"}}),
        encoding="utf-8",
    )
    assert abstain.mode_from_config(run) == "dense"

"""Sensitivity sweeps: three dose-response curves as configuration (ticket 13).

The expectations below are written out literally, from spec.md rows 2-4, ADR-0011
and the abstention working points, so the tests do not recompute the design the way
`ragqa.sweeps` does. The rule under test is ceteris paribus: one point of a sweep
differs from the sweep base in exactly the one parameter it is sweeping, and every
other key -- corpus, golden set, retrieval mode, rerank truncation, prices -- is
byte-identical. A sweep that quietly moves a second knob produces a number that
looks like evidence and is not (ADR-0003).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import statistics
import tempfile

from ragqa import config as config_mod
from ragqa import grid
from ragqa import sweeps

REFERENCE_CELL = os.path.join(
    "configs", "grid", "cell-recursive_parent_child-rerank-plain.yaml"
)

#: spec.md rows 2-4: every sweep runs over the 40 answerable items of golden v1,
#: selected by the `answerable` flag into a derived file rather than by taking the
#: first 40 lines. The old positional limit happened to select the same items and
#: would have silently stopped doing so on any reordering of v1.
ANSWERABLE_ITEMS = 40
ANSWERABLE_GOLDEN = "golden/v1-answerable.jsonl"

#: Differences from the *sweep base* (the reference cell on the derived answerable
#: golden set), restated by hand. `run.name` is a derived label, asserted separately.
EXPECTED_DIFF = {
    "k-05": {"retrieval.k"},
    "k-10": set(),
    "k-20": {"retrieval.k", "retrieval.rerank_top"},
    "k-40": {"retrieval.k", "retrieval.rerank_top"},
    "chunk-256": {"chunk.size", "chunk.overlap", "chunk.parent_size"},
    "chunk-512": set(),
    "chunk-1024": {"chunk.size", "chunk.overlap", "chunk.parent_size"},
    "hops-1": {"retrieval.hop_rewrite_model", "retrieval.trigger_threshold"},
    "hops-2": {
        "retrieval.hops",
        "retrieval.hop_rewrite_model",
        "retrieval.trigger_threshold",
    },
    "hops-3": {
        "retrieval.hops",
        "retrieval.hop_rewrite_model",
        "retrieval.trigger_threshold",
    },
}

#: Keys that are design-wide constants: they may differ from the reference cell in
#: the same way for every sweep point, and must never vary within the sweep.
CONSTANT_KEYS = (
    "corpus.source",
    "corpus.snapshot_id",
    "golden.items_path",
    "golden.limit",
    "retrieval.mode",
    "retrieval.rerank_max_length",
    "retrieval.reranker",
    "llm.model_generate",
    "llm.price_in_usd_per_mtok",
    "llm.price_out_usd_per_mtok",
    "chunk.strategy",
    "context.mode",
)

#: ADR-0011: the effective candidate depth must keep at least k candidates.
DEPTH = {5: 12, 10: 12, 20: 20, 40: 40}

#: Overlap keeps the reference ratio (64/512 = 1/8) and the parent budget keeps the
#: reference ratio to the child budget (1024/512 = 2), so chunking stays the same
#: shape and only its resolution moves.
CHUNK = {256: (32, 512), 512: (64, 1024), 1024: (128, 2048)}


def _tmpdir() -> str:
    return tempfile.mkdtemp(prefix="sweeps-test-")


def _load(name: str, directory: str = None) -> config_mod.Config:
    directory = directory or sweeps.DEFAULT_CONFIG_DIR
    return config_mod.load(os.path.join(directory, name + ".yaml"))


def _values(cfg: config_mod.Config) -> dict:
    return cfg.as_dict()


def _diff(left: dict, right: dict) -> set:
    """Every key whose resolved value differs -- the full key diff, not a spot check."""
    return {key for key in left if left[key] != right[key]}


# --- the declaration -------------------------------------------------------


def test_every_cell_loads_and_differs_from_the_sweep_base_in_one_parameter():
    out = _tmpdir()
    try:
        paths = sweeps.emit(out)
        assert len(paths) == 10, [str(path) for path in paths]
        base = sweeps.reference_values()
        reference = _values(config_mod.load(REFERENCE_CELL))

        for name in sorted(EXPECTED_DIFF):
            cfg = _load(name, out)
            values = _values(cfg)
            assert values["golden.limit"] is None, name
            assert values["golden.items_path"] == ANSWERABLE_GOLDEN, name

            # The whole key diff against the sweep base, asserted as a set.
            assert _diff(values, base) == EXPECTED_DIFF[name] | {"run.name"}, (
                name,
                sorted(_diff(values, base) - EXPECTED_DIFF[name] - {"run.name"}),
            )
            # And against the reference cell the same diff plus the golden stratum.
            assert _diff(values, reference) == (
                EXPECTED_DIFF[name] | {"golden.items_path", "run.name"}
            ), (name, sorted(_diff(values, reference)))

            # The derived label tracks the point and nothing else.
            assert values["run.name"] == "sweep-" + name, name
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_the_cells_of_one_family_differ_only_in_that_family_s_parameter():
    surfaces = {
        "k": {"retrieval.k", "retrieval.rerank_top", "run.name"},
        "chunk": {"chunk.size", "chunk.overlap", "chunk.parent_size", "run.name"},
        "hops": {"retrieval.hops", "run.name"},
    }
    out = _tmpdir()
    try:
        sweeps.emit(out)
        for family, allowed in surfaces.items():
            labels = [point.label for point in sweeps.family(family).points]
            values = {label: _values(_load(label, out)) for label in labels}
            for i, left in enumerate(labels):
                for right in labels[i + 1:]:
                    differing = _diff(values[left], values[right])
                    assert differing <= allowed, (family, left, right, sorted(differing))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_corpus_golden_set_mode_and_prices_are_design_wide_constants():
    out = _tmpdir()
    try:
        sweeps.emit(out)
        values = {
            name: _values(_load(name, out)) for name in sorted(EXPECTED_DIFF)
        }
        for key in CONSTANT_KEYS:
            seen = {values[name][key] for name in values}
            assert len(seen) == 1, (key, seen)
        # The stratum file, not the full set: 40 answerable items and no near-misses.
        assert values["k-40"]["golden.items_path"] == ANSWERABLE_GOLDEN, values["k-40"]
        assert values["k-40"]["golden.limit"] is None, values["k-40"]
        # Retrieval depth is swept only by the k family; the other two inherit 10.
        for name in ("chunk-1024", "hops-3"):
            assert values[name]["retrieval.k"] == 10, name
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_rerank_depth_is_at_least_k_in_every_k_cell():
    out = _tmpdir()
    try:
        sweeps.emit(out)
        for k, depth in DEPTH.items():
            cfg = _load("k-%02d" % k, out)
            assert cfg["retrieval.k"] == k
            assert cfg["retrieval.rerank_top"] == max(k, 12), k
            assert grid.depth_of(cfg) == depth, k
            assert grid.depth_of(cfg) >= cfg["retrieval.k"], k
        # The one value that would fake a recall@20 curve is depth 12 at k = 20.
        assert DEPTH[40] > 12
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_chunk_cells_keep_overlap_and_parent_size_proportional():
    out = _tmpdir()
    try:
        sweeps.emit(out)
        for size, (overlap, parent) in CHUNK.items():
            cfg = _load("chunk-%d" % size, out)
            assert cfg["chunk.size"] == size, size
            assert cfg["chunk.overlap"] == overlap, size
            assert cfg["chunk.parent_size"] == parent, size
            assert cfg["chunk.overlap"] * 8 == cfg["chunk.size"], size
            assert cfg["chunk.parent_size"] == 2 * cfg["chunk.size"], size
        # A chunk sweep that also moved k would measure two things at once.
        assert len({_load("chunk-%d" % size, out)["retrieval.k"] for size in CHUNK}) == 1
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_hop_cells_share_the_trigger_the_abstention_sweep_chose():
    """The trigger is the rerank working point: a rewrite fires where the system abstains.

    This is the property worth protecting, so it is read out of the published sweep
    rather than compared with a second literal: same score scale, same golden set,
    same number in all three hop cells so only the hop cap varies.
    """
    out = _tmpdir()
    try:
        sweeps.emit(out)
        hops = {}
        for count in (1, 2, 3):
            cfg = _load("hops-%d" % count, out)
            hops[count] = cfg["retrieval.hops"]
            assert cfg["retrieval.hops"] == count
            assert cfg["retrieval.hop_rewrite_model"] == "deepseek-v4.1-flash", count
            assert cfg["retrieval.trigger_threshold"] == sweeps.HOP_TRIGGER, count
        assert hops == {1: 1, 2: 2, 3: 3}

        working = json.load(open("reports/abstention/working-points.json", "r", encoding="utf-8"))
        rerank = working["modes"]["rerank"]
        # The same golden set the sweep cells measure on.
        assert rerank["golden"] == "golden/v1.jsonl", rerank["golden"]
        assert rerank["items"] == {"answerable": 40, "near_miss": 20, "total": 60}, rerank
        assert rerank["transform"]["kind"] == "zscore-normal-cdf", rerank
        assert abs(sweeps.HOP_TRIGGER - rerank["raw_threshold"]) < 5e-6, (
            "the hop trigger has drifted from the published rerank working point",
            sweeps.HOP_TRIGGER,
            rerank["raw_threshold"],
        )
        assert sweeps.HOP_TRIGGER_SOURCE["working_point_raw"] == sweeps.HOP_TRIGGER
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_emit_is_deterministic_and_check_accepts_the_declaration():
    first, second = _tmpdir(), _tmpdir()
    stdout = io.StringIO()
    try:
        sweeps.emit(first)
        sweeps.emit(second)
        names = sorted(os.listdir(first))
        assert names == sorted(os.listdir(second)), names
        for name in names:
            assert open(os.path.join(first, name), "rb").read() == open(
                os.path.join(second, name), "rb"
            ).read(), name
        with contextlib.redirect_stdout(stdout):
            assert sweeps.check([first]) == 0, stdout.getvalue()
        table = stdout.getvalue()
        for column in ("cell", "family", "x", "k", "depth", "items", "trigger", "hops"):
            assert column in table, column
    finally:
        shutil.rmtree(first, ignore_errors=True)
        shutil.rmtree(second, ignore_errors=True)


def test_check_fails_loudly_when_a_second_parameter_moves_or_depth_drops():
    out = _tmpdir()
    try:
        sweeps.emit(out)
        victim = os.path.join(out, "k-40.yaml")
        text = open(victim, "r", encoding="utf-8").read()

        # ADR-0011: hand-edited depth below k must not reach the runner.
        open(victim, "w", encoding="utf-8", newline="\n").write(
            text.replace("rerank_top: 40", "rerank_top: 12")
        )
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = sweeps.check([out])
        assert code != 0, "a depth below k was accepted"
        assert "ADR-0011" in stderr.getvalue(), stderr.getvalue()

        # A second knob silently moved: the diff is no longer the declared one.
        open(victim, "w", encoding="utf-8", newline="\n").write(
            text.replace("max_claims: 3", "max_claims: 5")
        )
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = sweeps.check([out])
        assert code != 0, "a two-parameter comparison was accepted"
        assert "generate.max_claims" in stderr.getvalue(), stderr.getvalue()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_check_rejects_a_cell_file_that_is_not_in_the_declaration():
    out = _tmpdir()
    try:
        sweeps.emit(out)
        stray = os.path.join(out, "k-07.yaml")
        open(stray, "w", encoding="utf-8", newline="\n").write(
            open(os.path.join(out, "k-05.yaml"), "r", encoding="utf-8").read()
        )
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = sweeps.check([out])
        assert code != 0, "a config that no sweep declares was accepted"
        assert "k-07" in stderr.getvalue(), stderr.getvalue()
    finally:
        shutil.rmtree(out, ignore_errors=True)


# --- the runner ------------------------------------------------------------


def _bomb(*args, **kwargs):
    raise AssertionError("a dry run must not execute the pipeline")


def test_dry_run_spends_nothing_and_prints_the_projected_call_count():
    out, base = _tmpdir(), _tmpdir()
    runs = os.path.join(base, "runs")
    original = sweeps._execute_cell
    sweeps._execute_cell = _bomb
    stdout = io.StringIO()
    try:
        sweeps.emit(out)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = sweeps.run([out], dry_run=True, out_root=runs)
        assert code == 0, stdout.getvalue()
        assert not os.path.exists(runs), "a dry run must not create anything under runs/"

        entries = sweeps.plan([out], out_root=runs)
        projected = sweeps.projection(entries)
        assert projected["cells"] == 10, projected
        assert projected["generation_calls"] == 400, projected
        assert projected["by_family"]["k"] == 160, projected
        assert projected["by_family"]["chunk"] == 120, projected
        assert projected["by_family"]["hops"] == 120, projected
        assert projected["rewrite_calls"] == 120, projected
        text = stdout.getvalue()
        assert "400" in text, text
        assert "120" in text, text
        assert "dry run" in text.lower(), text
    finally:
        sweeps._execute_cell = original
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_resume_skips_a_finished_point_and_force_reruns_it():
    out, base = _tmpdir(), _tmpdir()
    runs = os.path.join(base, "runs")
    try:
        sweeps.emit(out)
        done = sweeps.cell("hops-2")
        path = os.path.join(runs, "%s-20260101T000000-%s" % (done["run_name"], done["digest"]))
        os.makedirs(path)
        with open(os.path.join(path, "metrics.json"), "w", encoding="utf-8") as handle:
            json.dump({"retrieval": {"hit_rate": 1.0}}, handle)

        status = {entry["label"]: entry for entry in sweeps.plan([out], out_root=runs)}
        assert status["hops-2"]["status"] == "finished", status["hops-2"]
        assert status["hops-2"]["run_dir"] == path
        assert status["hops-1"]["status"] == "pending"
        assert sweeps.projection(list(status.values()))["remaining_calls"] == 9 * ANSWERABLE_ITEMS

        forced = sweeps.plan([out], out_root=runs, force=True)
        assert all(entry["status"] == "pending" for entry in forced)
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


# --- the curve reader ------------------------------------------------------


def _finished(
    root: str,
    label: str,
    *,
    recall: float,
    mrr: float,
    ndcg: float,
    cite_p: float,
    cite_r: float,
    span: float,
    over: float,
    p50: float,
    p95: float,
    tokens: int,
    cny: float,
    answers: int,
    stops: dict = None,
    mean_hops: float = 1.0,
) -> str:
    """A synthetic finished run directory: metrics, timings, hop stats, config."""
    cell = sweeps.cell(label)
    path = os.path.join(
        root, "%s-20260101T000000-%s" % (cell["run_name"], cell["digest"])
    )
    os.makedirs(path, exist_ok=True)
    metrics = {
        "items": {"total": answers, "answerable": answers, "unanswerable": 0},
        "retrieval": {
            "k": cell["config"]["retrieval.k"],
            "hit_rate": recall,
            "recall_at_k": recall,
            "mrr": mrr,
            "ndcg_at_10": ndcg,
            "misses": [],
        },
        "citations": {
            "claims": 10,
            "supported": int(round(cite_p * 10)),
            "citation_precision": cite_p,
            "citation_recall": cite_r,
            "span_hit_rate": span,
            "containment_failures": {},
        },
        "abstention": {"over_abstain_rate": over, "abstained_answerable": 0},
        "system": {
            "cost_per_1k_questions_cny": cny,
            "cost_components": {
                "generation": {"tokens_in": tokens, "tokens_out": 0, "usd": 0.0}
            },
        },
    }
    with open(os.path.join(path, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(metrics, handle)
    with open(os.path.join(path, "timings.json"), "w", encoding="utf-8") as handle:
        json.dump({"p50_ms": p50, "p95_ms": p95}, handle)
    with open(os.path.join(path, "hop_stats.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "max_hops": cell["config"]["retrieval.hops"],
                "trigger_threshold": sweeps.HOP_TRIGGER,
                "stop_reasons": stops or {"hit_first_round": answers},
                "mean_hops": mean_hops,
            },
            handle,
        )
    with open(os.path.join(path, "config.json"), "w", encoding="utf-8") as handle:
        json.dump(cell["config"].nested(), handle)
    return path


def test_curve_reader_computes_hop_deltas_stop_histogram_and_cost_per_thousand():
    base = _tmpdir()
    runs, reports = os.path.join(base, "runs"), os.path.join(base, "reports")
    try:
        _finished(
            runs, "hops-1",
            recall=0.60, mrr=0.50, ndcg=0.55, cite_p=0.90, cite_r=0.60, span=0.40,
            over=0.05, p50=100.0, p95=260.0, tokens=1000, cny=5.0, answers=40,
            stops={"hit_first_round": 34, "cap_reached": 6}, mean_hops=1.0,
        )
        _finished(
            runs, "hops-2",
            recall=0.70, mrr=0.58, ndcg=0.62, cite_p=0.88, cite_r=0.70, span=0.45,
            over=0.05, p50=160.0, p95=410.0, tokens=1600, cny=8.0, answers=40,
            stops={"hit_first_round": 34, "hit_after_rewrite": 4, "cap_reached": 2},
            mean_hops=1.15,
        )
        _finished(
            runs, "hops-3",
            recall=0.72, mrr=0.59, ndcg=0.63, cite_p=0.87, cite_r=0.71, span=0.46,
            over=0.05, p50=240.0, p95=620.0, tokens=2400, cny=12.0, answers=40,
            stops={"hit_first_round": 34, "hit_after_rewrite": 5, "cap_reached": 1},
            mean_hops=1.25,
        )

        rows = sweeps.read_curve("hops", runs_root=runs)
        assert [row["label"] for row in rows] == ["hops-1", "hops-2", "hops-3"]
        assert [row["status"] for row in rows] == ["finished"] * 3
        by_label = {row["label"]: row for row in rows}

        assert by_label["hops-1"]["recall_at_k"] == 0.60
        assert by_label["hops-2"]["delta_recall"] == 0.10
        assert by_label["hops-3"]["delta_recall"] == 0.12
        assert by_label["hops-2"]["delta_citation_precision"] == -0.02
        assert by_label["hops-2"]["delta_p50_ms"] == 60.0
        assert by_label["hops-3"]["delta_cny_per_1k"] == 7.0

        # The break-even arithmetic the report needs: marginal ¥ per recall point.
        assert by_label["hops-2"]["incremental_cny_per_recall_point"] == 30.0
        assert by_label["hops-3"]["incremental_cny_per_recall_point"] == 200.0
        assert sweeps.break_even_hop(rows) == 2, sweeps.break_even_hop(rows)

        # The stop-reason histogram travels with the row.
        assert by_label["hops-2"]["stop_hit_after_rewrite"] == 4
        assert by_label["hops-2"]["stop_cap_reached"] == 2
        assert by_label["hops-3"]["mean_hops"] == 1.25

        code = sweeps.curve("hops", runs_root=runs, out=reports)
        assert code == 0
        csv_path = os.path.join(reports, "hops.csv")
        md_path = os.path.join(reports, "hops.md")
        assert os.path.isfile(csv_path) and os.path.isfile(md_path)
        table = open(csv_path, "r", encoding="utf-8").read()
        for column in (
            "label", "run_id", "recall_at_k", "mrr", "ndcg_at_10", "citation_precision",
            "citation_recall", "span_hit_rate", "over_abstain_rate", "p50_ms", "p95_ms",
            "tokens", "cny_per_1k", "mean_hops", "stop_hit_first_round",
            "stop_hit_after_rewrite", "stop_cap_reached", "delta_recall",
            "delta_citation_precision", "delta_p50_ms", "delta_cny_per_1k",
        ):
            assert column in table, column
        note = open(md_path, "r", encoding="utf-8").read()
        assert "hops-2" in note and "30.0" in note, note
        assert "break-even" in note.lower() or "stops paying" in note.lower(), note
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_curve_marks_points_pending_instead_of_inventing_numbers():
    base = _tmpdir()
    runs, reports = os.path.join(base, "runs"), os.path.join(base, "reports")
    os.makedirs(runs)
    stdout = io.StringIO()
    try:
        # One finished point only: the other three have no run directory at all.
        _finished(
            runs, "k-10",
            recall=0.9, mrr=0.8, ndcg=0.85, cite_p=0.9, cite_r=0.9, span=0.5,
            over=0.0, p50=90.0, p95=200.0, tokens=900, cny=4.0, answers=40,
        )
        rows = sweeps.read_curve("k", runs_root=runs)
        assert [row["status"] for row in rows] == [
            "pending", "finished", "pending", "pending"
        ], [(row["label"], row["status"]) for row in rows]
        finished = rows[1]
        assert finished["label"] == "k-10" and finished["x"] == 10
        assert finished["recall_at_k"] == 0.9
        pending = rows[2]
        assert pending["recall_at_k"] is None, pending
        assert pending["run_id"] == "", pending

        with contextlib.redirect_stdout(stdout):
            assert sweeps.curve("k", runs_root=runs, out=reports) == 0
        table = open(os.path.join(reports, "k.csv"), "r", encoding="utf-8").read()
        assert "pending" in table, table
        note = open(os.path.join(reports, "k.md"), "r", encoding="utf-8").read()
        assert "pending" in note.lower(), note
        # The command the integrator must run to fill the missing rows is printed.
        assert "run_sweeps.py" in note or "ragqa sweep" in note, note
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_curve_reports_a_loop_that_never_fires_as_stopping_at_the_first_hop():
    base = _tmpdir()
    runs = os.path.join(base, "runs")
    try:
        for count in (1, 2, 3):
            _finished(
                runs, "hops-%d" % count,
                recall=0.90, mrr=0.80, ndcg=0.85, cite_p=0.90, cite_r=0.90, span=0.5,
                over=0.0, p50=100.0 + 60.0 * (count - 1), p95=200.0, tokens=900,
                cny=4.0 + 4.0 * (count - 1), answers=40,
                stops={"hit_first_round": 40}, mean_hops=1.0,
            )
        rows = sweeps.read_curve("hops", runs_root=runs)
        assert all(row["delta_recall"] == 0.0 for row in rows), rows
        assert sweeps.break_even_hop(rows) == 1, sweeps.break_even_hop(rows)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# --- the golden stratum (finding 7a) ---------------------------------------


def test_emit_writes_the_answerable_stratum_of_golden_v1():
    """Selected by the `answerable` flag, not by position in the file."""
    out = _tmpdir()
    golden = os.path.join(out, "v1-answerable.jsonl")
    try:
        summary = sweeps.write_answerable_golden(out=golden)
        assert summary["items"] == ANSWERABLE_ITEMS, summary
        assert summary["negatives"] == 0, summary

        import json

        seeded = [
            json.loads(line)
            for line in open("golden/v1.jsonl", encoding="utf-8")
            if line.strip()
        ]
        expected = [item["id"] for item in seeded if item.get("answerable", True)]
        written = [
            json.loads(line) for line in open(golden, encoding="utf-8") if line.strip()
        ]
        assert [item["id"] for item in written] == expected, "wrong items or wrong order"
        assert len(expected) == ANSWERABLE_ITEMS, len(expected)
        assert all(item.get("answerable", True) for item in written)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_check_refuses_a_positional_item_limit():
    """`golden.limit` selects by line order, which is not a stratum."""
    out = _tmpdir()
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        sweeps.emit(out)
        victim = os.path.join(out, "k-10.yaml")
        text = open(victim, encoding="utf-8").read()
        with open(victim, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("limit: null", "limit: 40"))
        problems = sweeps._golden_problems("k-10", _load("k-10", out))
        assert len(problems) == 1, problems
        assert "position in the file" in problems[0], problems[0]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            assert sweeps.check([out]) != 0
        assert "position in the file" in stderr.getvalue(), stderr.getvalue()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_the_curve_says_how_many_near_miss_items_each_point_had():
    """A rate with no denominator prints n/a, never 0.0000.

    The sweep cells measure on the 40 answerable items, so every point has zero
    near-misses: the old table printed 0.0 for its abstention columns, which reads
    as a measurement of 0/0.
    """
    row = {column: None for column in sweeps.CURVE_COLUMNS}
    row.update(
        {
            "label": "k-10",
            "family": "k",
            "status": "finished",
            "run_id": "sweep-k-10-20260101T000000-abcdef12",
            "answers": 40,
            "negatives": 0,
            "over_abstain_rate": 0.05,
            "abstention_recall_on_near_misses": 0.0,
            "under_abstain_rate": 0.0,
        }
    )
    assert "negatives" in sweeps.CURVE_COLUMNS
    assert sweeps._md_table_cell(row, "negatives") == "0"
    assert sweeps._md_table_cell(row, "abstention_recall_on_near_misses") == "n/a (0 near-miss)"
    assert sweeps._md_table_cell(row, "under_abstain_rate") == "n/a (0 near-miss)"
    assert sweeps._md_table_cell(row, "over_abstain_rate") == "0.0500"

    row["negatives"] = 20
    row["abstention_recall_on_near_misses"] = 0.0
    assert sweeps._md_table_cell(row, "abstention_recall_on_near_misses") == "0.0000"

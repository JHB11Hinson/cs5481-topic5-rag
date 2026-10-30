"""The experiment matrix: one declaration, eighteen cells, one runner.

The factor levels below are written out literally, from the spec inventory and
ADR-0006, so the tests do not recompute the design the way `ragqa.grid` does.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile

from ragqa import config as config_mod
from ragqa import grid

# The design, restated independently of the module under test (spec.md row 1,
# ADR-0006). Subtracting `late_chunking` must leave a complete 2 x 3 x 2.
CHUNK_LEVELS = ["fixed", "recursive_parent_child"]
RETRIEVAL_LEVELS = ["dense", "hybrid", "rerank"]
CONTEXT_LEVELS = ["plain", "contextual_prefix", "late_chunking"]
PLANNED_ITEMS = 60


def _tmpdir() -> str:
    return tempfile.mkdtemp(prefix="grid-test-")


def _yaml_names(directory: str) -> list:
    return sorted(name for name in os.listdir(directory) if name.endswith(".yaml"))


def test_emit_writes_one_config_per_design_cell():
    out = _tmpdir()
    try:
        paths = grid.emit(out_dir=out)
        assert len(paths) == 18, len(paths)
        names = _yaml_names(out)
        assert len(names) == 18, names
        expected = {
            f"cell-{chunk}-{retrieval}-{context}.yaml"
            for chunk in CHUNK_LEVELS
            for retrieval in RETRIEVAL_LEVELS
            for context in CONTEXT_LEVELS
        }
        assert set(names) == expected, sorted(expected ^ set(names))
    finally:
        shutil.rmtree(out, ignore_errors=True)


#: Every key the three factor *levels* may touch. Anything outside this set
#: differing between two cells is a two-variable comparison (ADR-0003).
FACTOR_SURFACE = {
    "chunk.strategy",
    "retrieval.mode",
    "retrieval.rerank_top",
    "generate.abstain_score_threshold",
    "context.mode",
    "run.name",
}

#: Labels derived from the factors rather than knobs of their own: a run
#: directory has to say which cell it belongs to.
DERIVED_LABELS = {"run.name"}


def _load_cells(out: str) -> dict:
    cells = {}
    for name in _yaml_names(out):
        cfg = config_mod.load(os.path.join(out, name))
        cells[name] = cfg
    return cells


def test_every_cell_loads_and_the_factors_vary_independently():
    out = _tmpdir()
    try:
        grid.emit(out_dir=out)
        cells = _load_cells(out)

        # No duplicated cell: each (chunk, retrieval, context) triple exactly once.
        triples = [
            (
                cfg["chunk.strategy"],
                cfg["retrieval.mode"],
                cfg["context.mode"],
            )
            for cfg in cells.values()
        ]
        assert len(set(triples)) == 18, len(set(triples))
        assert set(triples) == {
            (chunk, retrieval, context)
            for chunk in CHUNK_LEVELS
            for retrieval in RETRIEVAL_LEVELS
            for context in CONTEXT_LEVELS
        }

        # The name is the factors: a cell cannot be named one way and built another.
        for name, cfg in cells.items():
            stem = name[: -len(".yaml")].split("-")
            assert stem[0] == "cell"
            chunk, retrieval, context = stem[1], stem[2], stem[3]
            assert cfg["chunk.strategy"] == chunk, name
            assert cfg["retrieval.mode"] == retrieval, name
            assert cfg["context.mode"] == context, name

        # Ceteris paribus: two cells may differ only where their factors differ.
        names = sorted(cells)
        for left in names:
            for right in names:
                if left >= right:
                    continue
                a, b = cells[left].as_dict(), cells[right].as_dict()
                differing = {key for key in a if a[key] != b[key]}
                assert differing <= FACTOR_SURFACE, (left, right, differing - FACTOR_SURFACE)

        # Changing one factor level alone moves nothing else: plain -> prefix is
        # the context factor and the context mode, not a bonus tuning change.
        for chunk in CHUNK_LEVELS:
            for retrieval in RETRIEVAL_LEVELS:
                plain = cells[f"cell-{chunk}-{retrieval}-plain.yaml"].as_dict()
                prefixed = cells[f"cell-{chunk}-{retrieval}-contextual_prefix.yaml"].as_dict()
                differing = {key for key in plain if plain[key] != prefixed[key]}
                assert differing - DERIVED_LABELS == {"context.mode"}, (chunk, retrieval, differing)

        # The derived label tracks the factors and nothing else.
        for name, cfg in cells.items():
            factors = name[: -len(".yaml")].split("-", 1)[1]
            assert cfg["run.name"] == "grid-" + factors, name

        # The golden set, corpus, k and generator are design-wide constants.
        for key in ("golden.items_path", "corpus.snapshot_id", "retrieval.k", "llm.model_generate"):
            values = {cfg.as_dict()[key] for cfg in cells.values()}
            assert len(values) == 1, (key, values)

        # ADR-0011: a reranked cell keeps at least k candidates after rescoring.
        for name, cfg in cells.items():
            k = int(cfg["retrieval.k"])
            if cfg["retrieval.mode"] == "rerank":
                assert int(cfg["retrieval.rerank_top"]) >= k, name
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_two_emits_are_byte_identical():
    first, second = _tmpdir(), _tmpdir()
    try:
        grid.emit(out_dir=first)
        grid.emit(out_dir=second)
        assert _yaml_names(first) == _yaml_names(second)
        for name in _yaml_names(first) + [grid.MANIFEST_NAME]:
            with open(os.path.join(first, name), "rb") as handle:
                before = handle.read()
            with open(os.path.join(second, name), "rb") as handle:
                after = handle.read()
            assert before == after, name
    finally:
        shutil.rmtree(first, ignore_errors=True)
        shutil.rmtree(second, ignore_errors=True)


def test_excluding_late_chunking_leaves_a_complete_twelve_cell_matrix():
    out = _tmpdir()
    try:
        grid.emit(out_dir=out)
        paths = grid.emit(out_dir=out, exclude=["late_chunking"])
        assert len(paths) == 12, len(paths)
        names = _yaml_names(out)
        assert len(names) == 12, names
        expected = {
            f"cell-{chunk}-{retrieval}-{context}.yaml"
            for chunk in CHUNK_LEVELS
            for retrieval in RETRIEVAL_LEVELS
            for context in ["plain", "contextual_prefix"]
        }
        assert set(names) == expected, sorted(expected ^ set(names))
        assert grid.check([out]) == 0, "the degraded matrix must still validate"

        manifest = grid.read_manifest(out)
        assert manifest["schema"] == grid.MANIFEST_SCHEMA
        assert len(manifest["cells"]) == 12
        assert manifest["factors"]["context.mode"] == ["plain", "contextual_prefix"]
    finally:
        shutil.rmtree(out, ignore_errors=True)


def _digest(cfg) -> str:
    """The documented run-id digest recipe, restated: sha256 of the resolved tree."""
    payload = json.dumps(cfg.nested(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:8]


def _finished_run(root: str, directory: str, with_config=None) -> str:
    """Fabricate a finished run directory: metrics.json and nothing real."""
    path = os.path.join(root, directory)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({"retrieval": {"hit_rate": 1.0}}, handle)
    if with_config is not None:
        with open(os.path.join(path, "config.json"), "w", encoding="utf-8") as handle:
            json.dump(with_config.nested(), handle)
    return path


def test_dry_run_projection_is_items_times_cells():
    out, base = _tmpdir(), _tmpdir()
    runs = os.path.join(base, "runs")
    try:
        grid.emit(out_dir=out)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = grid.run([out], dry_run=True, out_root=runs)
        assert code == 0, captured.getvalue()
        assert not os.path.exists(runs), "a dry run must not create anything under runs/"

        entries = grid.plan([out], out_root=runs)
        projected = grid.projection(entries)
        assert projected["cells"] == 18, projected
        assert projected["generation_calls"] == 18 * PLANNED_ITEMS
        assert projected["generation_calls"] == 1080, "spec.md row 1: 18 cells x 60 items"
        assert "1080" in captured.getvalue(), captured.getvalue()
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_projection_guard_fires_on_a_corrupted_expectation():
    out = _tmpdir()
    try:
        grid.emit(out_dir=out)
        projected = grid.projection(grid.plan([out], out_root=os.path.join(out, "runs")))
        calls = projected["generation_calls"]

        assert grid.compare_projection(calls, 1080)["ok"] is True
        assert grid.compare_projection(calls, 1120)["ok"] is True, "3.7% is inside the 5% band"
        assert grid.compare_projection(calls, 1140)["ok"] is False, "5.6% is outside it"

        corrupted = grid.compare_projection(calls, 900)
        assert corrupted["ok"] is False
        try:
            grid.assert_projection(corrupted)
        except grid.GridError as error:
            assert "grid bug" in str(error).lower(), str(error)
        else:
            raise AssertionError("a 20% projection miss was not reported as a grid bug")
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_skip_logic_recognises_a_finished_cell_and_force_reruns_it():
    out, base = _tmpdir(), _tmpdir()
    runs = os.path.join(base, "runs")
    try:
        grid.emit(out_dir=out)
        by_stem = {
            name[: -len(".yaml")]: config_mod.load(os.path.join(out, name))
            for name in _yaml_names(out)
        }

        # Recognised by the digest suffix run_id_for appends to every run directory.
        named = "cell-fixed-dense-plain"
        named_dir = _finished_run(
            runs, f"grid-fixed-dense-plain-20260101T000000-{_digest(by_stem[named])}"
        )
        # Recognised by the resolved config.json inside it, whatever it is called.
        recovered = "cell-recursive_parent_child-rerank-late_chunking"
        recovered_dir = _finished_run(runs, "recovered-20260101T000000", by_stem[recovered])
        # Not recognised: a run directory without metrics.json measured nothing.
        _finished_run(runs, "grid-fixed-dense-contextual_prefix-crashed")

        entries = grid.plan([out], out_root=runs)
        status = {entry["cell"]: entry for entry in entries}
        assert status[named]["status"] == "finished", status[named]
        assert status[named]["run_dir"] == named_dir
        assert status[recovered]["status"] == "finished", status[recovered]
        assert status[recovered]["run_dir"] == recovered_dir
        assert status["cell-fixed-dense-contextual_prefix"]["status"] == "pending"
        finished = [cell for cell, entry in status.items() if entry["status"] == "finished"]
        assert len(finished) == 2, finished

        projected = grid.projection(entries)
        assert projected["cells"] == 18
        assert projected["generation_calls"] == 1080, "the design total does not shrink"
        assert projected["remaining_calls"] == 16 * PLANNED_ITEMS
        assert projected["finished_cells"] == 2

        forced = grid.plan([out], out_root=runs, force=True)
        assert all(entry["status"] == "pending" for entry in forced), "force re-runs everything"
    finally:
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def test_check_prints_the_table_and_fails_loudly_on_a_broken_cell():
    out = _tmpdir()
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        grid.emit(out_dir=out)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            assert grid.check([out]) == 0
        table = stdout.getvalue()
        for column in ("cell", "chunk", "retrieval", "context", "k", "depth", "abstain", "golden"):
            assert column in table, column
        assert "cell-fixed-dense-plain" in table
        assert "v1.jsonl" in table, "the golden path each cell will consume"

        # ADR-0011: hand-edited depth below k must not reach the runner.
        victim = os.path.join(out, "cell-fixed-rerank-plain.yaml")
        with open(victim, "r", encoding="utf-8") as handle:
            text = handle.read()
        with open(victim, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("rerank_top: 12", "rerank_top: 4"))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = grid.check([out])
        assert code != 0, "a depth below k was accepted"
        assert "ADR-0011" in stderr.getvalue(), stderr.getvalue()

        # The closed schema: an unknown key is a typo, not a knob.
        broken = os.path.join(out, "cell-broken.yaml")
        with open(broken, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "corpus:\n  source: x\n  snapshot_id: y\nretrieval:\n  mode: dense\n  deepth: 3\n"
            )
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = grid.check([out])
        assert code != 0, "an unknown key was accepted"
        assert "retrieval.deepth" in stderr.getvalue(), stderr.getvalue()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_manifest_maps_cells_to_configs_and_run_ids():
    out = _tmpdir()
    try:
        grid.emit(out_dir=out)
        manifest = grid.read_manifest(out)
        entries = {entry["cell"]: entry for entry in manifest["cells"]}
        assert len(entries) == 18
        assert manifest["factors"]["retrieval.mode"] == list(RETRIEVAL_LEVELS)
        assert manifest["factor_keys"] == {
            "chunk_strategy": "chunk.strategy",
            "retrieval_mode": "retrieval.mode",
            "context_mode": "context.mode",
        }
        for name, entry in entries.items():
            assert entry["config_file"] == name + ".yaml"
            assert os.path.isfile(os.path.join(out, entry["config_file"])), name
            assert entry["run_id_pattern"] == "{}-*-{}".format(
                entry["run_name"], entry["config_digest"]
            )
            assert entry["expected_items"] == PLANNED_ITEMS
            assert entry["factors"] == {
                "chunk_strategy": name.split("-")[1],
                "retrieval_mode": name.split("-")[2],
                "context_mode": name.split("-")[3],
            }
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_a_stale_manifest_digest_is_caught_even_when_the_cell_names_match():
    """Same 18 files, one edited: the names still match and the digest does not.

    Names alone passed this, and `aggregate` would then have reported a finished
    cell as absent while its run sat in the run root under a digest nothing matched.
    """
    out = _tmpdir()
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        grid.emit(out_dir=out)
        manifest = grid.read_manifest(out)
        assert grid._manifest_problems([out]) == []

        victim = os.path.join(out, "cell-fixed-hybrid-plain.yaml")
        with open(victim, "r", encoding="utf-8") as handle:
            text = handle.read()
        # A loadable change that moves the resolved configuration and therefore the
        # digest, so the file list stays identical.
        with open(victim, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("abstain_score_threshold: 0.01", "abstain_score_threshold: 0.02"))

        problems = grid._manifest_problems([out])
        assert len(problems) == 1, problems
        assert "cell-fixed-hybrid-plain" in problems[0], problems[0]
        assert "re-run `grid emit`" in problems[0], problems[0]

        before = {entry["cell"]: entry["config_digest"] for entry in manifest["cells"]}
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            assert grid.check([out]) != 0, "a stale manifest digest was accepted"
        assert "cell-fixed-hybrid-plain" in stderr.getvalue(), stderr.getvalue()

        # Re-emitting rebuilds both sides from the declaration, so they agree again.
        grid.emit(out_dir=out)
        after = {
            entry["cell"]: entry["config_digest"]
            for entry in grid.read_manifest(out)["cells"]
        }
        assert after == before, "emit is a pure function of the declaration"
        assert grid._manifest_problems([out]) == []
    finally:
        shutil.rmtree(out, ignore_errors=True)

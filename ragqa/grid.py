"""The eighteen-cell matrix, declared once and executed by a resumable runner.

The design is a factorial 2 x 3 x 3 (ADR-0006, spec.md row 1): chunk strategy
{2} x retrieval mode {3} x contextualization {3}. Every cell is a configuration
file, so the code stays constant and only the named factors move (ADR-0003).

    python -m ragqa grid emit      # write configs/grid/*.yaml + grid.json
    python -m ragqa grid check     # load every cell through the closed schema
    python -m ragqa grid run       # execute cells, skipping finished ones

A cell's name encodes its factors (`cell-<chunk>-<retrieval>-<context>`), so a
run directory, a report row and a config file can be matched by eye. The one
exception to "only the factors differ" is deliberate and is part of the level
rather than a separate knob: a retrieval mode is measured on its own score scale
(cosine, RRF-fused, cross-encoder logits), so each retrieval level carries the
abstention threshold that belongs to that scale.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml

from . import config as config_mod

# ---- the declaration -------------------------------------------------------

CHUNK_STRATEGIES: Sequence[str] = ("fixed", "recursive_parent_child")
RETRIEVAL_MODES: Sequence[str] = ("dense", "hybrid", "rerank")
CONTEXT_MODES: Sequence[str] = ("plain", "contextual_prefix", "late_chunking")

#: One cell changes exactly one of these three keys' *level*; everything else is
#: shared, so a difference between two cells is attributable to one factor. The
#: short names are what the manifest and the aggregate step speak.
FACTOR_KEYS = {
    "chunk_strategy": "chunk.strategy",
    "retrieval_mode": "retrieval.mode",
    "context_mode": "context.mode",
}

#: The full-strength cell: real corpus, real embedding model, real index, real
#: generator. Endpoint and key are not here -- `LLMClient` reads LLM_BASE_URL and
#: LLM_API_KEY from the environment (AGENTS.md: no endpoints in files).
BASELINE: Dict[str, Any] = {
    "run": {"out_root": "runs"},
    "corpus": {
        "source": "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl",
        "snapshot_id": "vault-1.21.x-1817bdfe",
    },
    "chunk": {"size": 512, "overlap": 64, "parent_size": 1024},
    "embed": {
        "provider": "bge-m3",
        "model_id": "BAAI/bge-m3",
        "device": "cuda",
        "batch_size": 8,
        "max_seq_length": 1024,
        "late_max_seq_length": 8192,
        "cache_path": "data/cache/embeddings.sqlite",
    },
    "index": {"backend": "qdrant", "path": "data/index"},
    "retrieval": {
        "k": 10,
        "rrf_k": 60,
        "reranker": "BAAI/bge-reranker-v2-m3",
        "rerank_max_length": 512,
    },
    # Present in every cell, not only the prefixed ones: a factor must be the
    # only thing that differs between two cells, so the prefixer is configured
    # (and idle) everywhere.
    "context": {
        "prefix_model": "deepseek-v4.1-flash",
        "window_tokens": 2048,
        "window_overlap": 256,
    },
    "generate": {
        "provider": "llm",
        "model_id": "llm",
        "min_claim_overlap": 0.12,
        "max_claims": 3,
    },
    "llm": {
        "model_generate": "deepseek-v4.1-flash",
        "model_judge": "deepseek-v4-pro",
        "cache_path": "data/cache/llm.sqlite",
        "timeout": 180,
        "temperature": 0.0,
        "max_tokens": 1600,
        "context_chunks": 8,
        "price_in_usd_per_mtok": 0.15,
        "price_out_usd_per_mtok": 0.60,
    },
    "golden": {"items_path": "golden/v1.jsonl"},
}

#: The retrieval factor is a level, not just a mode name: each mode is scored on
#: its own scale, so the abstention threshold travels with the level (see the
#: note in `configs/real_hybrid.yaml`). Retrieval depth is checked against k by
#: `depth_of` -- ADR-0011.
RETRIEVAL_LEVELS: Dict[str, Dict[str, Any]] = {
    "dense": {"retrieval.mode": "dense", "generate.abstain_score_threshold": 0.20},
    "hybrid": {"retrieval.mode": "hybrid", "generate.abstain_score_threshold": 0.01},
    "rerank": {
        "retrieval.mode": "rerank",
        "retrieval.rerank_top": 12,
        "generate.abstain_score_threshold": 0.0,
    },
}

CONTEXT_LEVELS: Dict[str, Dict[str, Any]] = {
    "plain": {"context.mode": "plain"},
    "contextual_prefix": {"context.mode": "contextual_prefix"},
    "late_chunking": {"context.mode": "late_chunking"},
}

#: Generation calls the spec inventory expects for a design of this many cells
#: (spec.md row 1: 18 cells x 60 items = 1,080). ADR-0006: the two-level
#: degradation of the same design is 12 cells x 60 = 720.
PLANNED_ITEMS = 60

MANIFEST_NAME = "grid.json"
MANIFEST_SCHEMA = "ragqa.grid/1"
DEFAULT_OUT_DIR = os.path.join("configs", "grid")


class GridError(RuntimeError):
    """A defect in the grid declaration or its projection, not a user mistake."""


# ---- declaration -> cells --------------------------------------------------


def _set(tree: Dict[str, Any], path: str, value: Any) -> None:
    node = tree
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def cell_name(chunk: str, retrieval: str, context: str) -> str:
    return f"cell-{chunk}-{retrieval}-{context}"


def declaration(exclude: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """The cells, in run order: chunk strategy, then retrieval, then context.

    `exclude` drops contextualization levels; excluding `late_chunking` is the
    degradation switch the ticket requires (ADR-0006 consequence), leaving a
    complete 2 x 3 x 2 design rather than a ragged half-matrix.
    """
    dropped = set(exclude or ())
    unknown = dropped - set(CONTEXT_MODES)
    if unknown:
        raise GridError(
            f"cannot exclude {sorted(unknown)}: known contextualization levels are "
            f"{list(CONTEXT_MODES)}"
        )
    cells: List[Dict[str, Any]] = []
    for chunk in CHUNK_STRATEGIES:
        for retrieval in RETRIEVAL_MODES:
            for context in CONTEXT_MODES:
                if context in dropped:
                    continue
                cells.append(_build_cell(chunk, retrieval, context))
    return cells


def _build_cell(chunk: str, retrieval: str, context: str) -> Dict[str, Any]:
    name = cell_name(chunk, retrieval, context)
    tree = copy.deepcopy(BASELINE)
    _set(tree, "run.name", f"grid-{chunk}-{retrieval}-{context}")
    _set(tree, "chunk.strategy", chunk)
    for patch in (RETRIEVAL_LEVELS[retrieval], CONTEXT_LEVELS[context]):
        for path, value in patch.items():
            _set(tree, path, value)
    return {
        "cell": name,
        "factors": {
            "chunk_strategy": chunk,
            "retrieval_mode": retrieval,
            "context_mode": context,
        },
        "tree": tree,
    }


def _render(tree: Dict[str, Any], cell: Dict[str, Any]) -> str:
    factors = cell["factors"]
    header = [
        f"# {cell['cell']} -- the factorial matrix (ticket 12). Generated by",
        "# `python -m ragqa grid emit`; edit `ragqa/grid.py`, never this file.",
        "#",
        f"#   chunk strategy   : {factors['chunk_strategy']}",
        f"#   retrieval mode   : {factors['retrieval_mode']}",
        f"#   contextualization: {factors['context_mode']}",
        "#",
        "# Cells differ from their neighbours only in those three factors.",
    ]
    body = yaml.safe_dump(tree, sort_keys=True, default_flow_style=False, width=100)
    return "\n".join(header) + "\n" + body


def emit(
    out_dir: Optional[str] = None,
    exclude: Optional[Iterable[str]] = None,
    inventory: bool = True,
) -> List[pathlib.Path]:
    """Write one YAML per cell plus, when `inventory`, the `grid.json` manifest.

    The output is a pure function of the declaration: two emits produce
    byte-identical files, so a config diff means the design changed.
    """
    directory = out_dir or DEFAULT_OUT_DIR
    os.makedirs(directory, exist_ok=True)
    cells = declaration(exclude)
    written: List[pathlib.Path] = []
    for cell in cells:
        path = os.path.join(directory, cell["cell"] + ".yaml")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_render(cell["tree"], cell))
        written.append(pathlib.Path(path))
    # The directory *is* the matrix: a cell left over from an earlier, larger
    # declaration would silently re-enter `check` and later `aggregate`.
    keep = {path.name for path in written}
    for name in os.listdir(directory):
        if name.startswith("cell-") and name.endswith(".yaml") and name not in keep:
            os.remove(os.path.join(directory, name))
    if inventory:
        _write_manifest(directory, cells)
    return written


# ---- identity of a cell ----------------------------------------------------


def config_digest(cfg: config_mod.Config) -> str:
    """The config's identity: the same eight hex characters `run_id_for` uses.

    Wall-clock stamps change every second, so a runner cannot recognise its own
    finished work by run id; it matches on this digest instead (ADR-0003: an
    immutable run directory belongs to exactly one resolved configuration).
    """
    payload = json.dumps(cfg.nested(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:8]


def _expected_items(cfg: config_mod.Config) -> int:
    """How many golden items this cell will generate for.

    The item count is a property of the Golden QA Set, not of the cell: unless a
    cell pins `golden.limit`, the full set is used, and the planned size of that
    set is the spec's 60. When the file is present its length wins, so the
    projection stays honest once v1 lands.
    """
    limit = cfg["golden.limit"]
    if limit:
        return int(limit)
    path = cfg["golden.items_path"]
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    return PLANNED_ITEMS


def _present(cells: List[Dict[str, Any]], key: str, level: str) -> bool:
    """Is this factor level still in the design? (The degradation switch drops one.)"""
    short = [name for name, path in FACTOR_KEYS.items() if path == key][0]
    return any(cell["factors"][short] == level for cell in cells)


def _write_manifest(directory: str, cells: List[Dict[str, Any]]) -> str:
    """`grid.json`: cell name -> factors -> config file -> the run it will make.

    `ragqa aggregate` reads this to join finished run directories back onto the
    design, so the schema is flat, versioned and free of paths that only made
    sense on the machine that emitted it.
    """
    entries = []
    for cell in cells:
        path = os.path.join(directory, cell["cell"] + ".yaml")
        cfg = config_mod.load(path)
        digest = config_digest(cfg)
        run_name = cfg["run.name"]
        entries.append(
            {
                "cell": cell["cell"],
                "factors": dict(cell["factors"]),
                "config_file": cell["cell"] + ".yaml",
                "run_name": run_name,
                "config_digest": digest,
                "run_id_pattern": f"{run_name}-*-{digest}",
                "expected_items": _expected_items(cfg),
            }
        )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "factor_keys": dict(FACTOR_KEYS),
        "factors": {
            key: [level for level in levels if _present(cells, key, level)]
            for key, levels in (
                ("chunk.strategy", CHUNK_STRATEGIES),
                ("retrieval.mode", RETRIEVAL_MODES),
                ("context.mode", CONTEXT_MODES),
            )
        },
        "cells": entries,
    }
    path = os.path.join(directory, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def read_manifest(directory: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(directory, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ---- run: resume, project, execute ----------------------------------------


def _digest_of_run_dir(path: str) -> str:
    """Identify a finished run by its resolved configuration, not its stamp.

    `config.json` is the run's own record of what was measured (ADR-0003), so it
    is authoritative; older directories that predate it are identified by the
    digest suffix `run_id_for` put in the name.
    """
    config_path = os.path.join(path, "config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                tree = json.load(handle)
        except (OSError, ValueError):
            tree = None
        if isinstance(tree, dict):
            payload = json.dumps(tree, sort_keys=True).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()[:8]
    tail = os.path.basename(path).rsplit("-", 1)[-1]
    if len(tail) == 8 and all(character in "0123456789abcdef" for character in tail):
        return tail
    return ""


def finished_runs(roots: Iterable[str]) -> Dict[str, str]:
    """digest -> run directory, over every run directory that produced metrics."""
    index: Dict[str, str] = {}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            if not os.path.isfile(os.path.join(path, "metrics.json")):
                continue
            digest = _digest_of_run_dir(path)
            if digest:
                index.setdefault(digest, path)
    return index


def plan(
    paths: Optional[Sequence[str]] = None,
    out_root: Optional[str] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """The run order, with each cell marked finished or pending.

    Finished means "a run directory with metrics.json already exists for this
    exact resolved configuration"; a crashed attempt deletes its directory, so
    there is no half-finished state to guess at (ADR-0003).
    """
    files = config_files(paths)
    cells: List[Dict[str, Any]] = []
    for path in files:
        cfg = config_mod.load(path)
        cells.append(
            {
                "cell": _cell_of(path),
                "config_path": path,
                "factors": {
                    "chunk_strategy": cfg["chunk.strategy"],
                    "retrieval_mode": cfg["retrieval.mode"],
                    "context_mode": cfg["context.mode"],
                },
                "run_name": cfg["run.name"],
                "config_digest": config_digest(cfg),
                "items": _expected_items(cfg),
                "out_root": out_root or cfg["run.out_root"],
                "status": "pending",
                "run_dir": "",
                "config": cfg,
            }
        )

    if not force:
        index = finished_runs({cell["out_root"] for cell in cells})
        for cell in cells:
            path = index.get(cell["config_digest"])
            if path:
                cell["status"] = "finished"
                cell["run_dir"] = path
    return cells


def projection(cells: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The design's generation-call total, and what is left of it.

    The design total is what the spec inventory is compared against; skipping a
    finished cell reduces `remaining_calls`, never the design.
    """
    by_cell = {cell["cell"]: int(cell["items"]) for cell in cells}
    finished = [cell for cell in cells if cell["status"] == "finished"]
    return {
        "cells": len(cells),
        "items_by_cell": by_cell,
        "generation_calls": sum(by_cell.values()),
        "finished_cells": len(finished),
        "remaining_calls": sum(
            by_cell[cell["cell"]] for cell in cells if cell["status"] != "finished"
        ),
    }


#: What the experiment inventory expects for a design of this size (spec.md row
#: 1: 18 cells x 60 items; ADR-0006: the degraded design is 12 x 60).
SPEC_INVENTORY: Dict[int, int] = {18: 1080, 12: 720}

PROJECTION_TOLERANCE = 0.05


def expected_calls(cell_count: int) -> int:
    try:
        return SPEC_INVENTORY[cell_count]
    except KeyError:
        raise GridError(
            f"no spec inventory row for a {cell_count}-cell design "
            f"(known: {sorted(SPEC_INVENTORY)})"
        )


def compare_projection(
    projected_calls: int, expected: int, tolerance: float = PROJECTION_TOLERANCE
) -> Dict[str, Any]:
    """Compare a projection against the inventory; a gap is a grid bug."""
    if expected <= 0:
        raise GridError(f"expected generation calls must be positive, got {expected}")
    delta = projected_calls - expected
    fraction = abs(delta) / float(expected)
    return {
        "ok": fraction <= tolerance,
        "projected": projected_calls,
        "expected": expected,
        "delta": delta,
        "fraction": round(fraction, 4),
        "tolerance": tolerance,
    }


def assert_projection(report: Dict[str, Any]) -> None:
    if not report["ok"]:
        raise GridError(
            "grid bug: projection is {} generation calls but the inventory expects {} "
            "({:+.1f}%, tolerance {:+.0f}%). The declaration does not match the design "
            "in spec.md -- fix the grid, do not spend money on it.".format(
                report["projected"],
                report["expected"],
                report["fraction"] * 100.0,
                report["tolerance"] * 100.0,
            )
        )


def run(
    paths: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    force: bool = False,
    out_root: Optional[str] = None,
) -> int:
    """Execute pending cells in declaration order; report what was produced."""
    try:
        cells = plan(paths, out_root=out_root, force=force)
    except GridError as error:
        print(f"PROBLEM {error}", file=sys.stderr)
        return 1
    if not cells:
        print("PROBLEM no configuration files found", file=sys.stderr)
        return 1

    projected = projection(cells)
    report = compare_projection(projected["generation_calls"], expected_calls(len(cells)))

    width = max(len(cell["cell"]) for cell in cells)
    print(
        f"grid: {projected['cells']} cell(s), {projected['generation_calls']} generation "
        f"call(s) for the design, {projected['remaining_calls']} remaining"
    )
    for position, cell in enumerate(cells, 1):
        print(
            "{:>2}. {:<{width}}  {:<8}  {:>3} item(s)  {:>4} call(s)  {}".format(
                position,
                cell["cell"],
                cell["status"],
                cell["items"],
                cell["items"],
                cell["run_dir"] or cell["run_name"] + "-*",
                width=width,
            )
        )
    print(
        "projection: {} projected vs {} expected for {} cells ({:+.1f}%, tolerance {:+.0f}%) "
        "-- {}".format(
            report["projected"],
            report["expected"],
            len(cells),
            report["fraction"] * 100.0,
            report["tolerance"] * 100.0,
            "ok" if report["ok"] else "MISMATCH",
        )
    )

    try:
        assert_projection(report)
    except GridError as error:
        print(f"{error}", file=sys.stderr)
        return 1

    if dry_run:
        print("dry run: nothing executed, nothing spent")
        return 0

    from . import run as run_mod

    produced: List[str] = []
    failures: List[str] = []
    calls = 0
    for position, cell in enumerate(cells, 1):
        prefix = f"[{position}/{len(cells)}] {cell['cell']}"
        if cell["status"] == "finished":
            print(f"{prefix}: finished at {cell['run_dir']}, skipped")
            continue
        try:
            result = run_mod.execute(cell["config"], cell["out_root"])
        except Exception as error:  # a cell that dies must not stop the matrix
            failures.append(f"{cell['cell']}: {error}")
            print(f"{prefix}: FAILED ({error})", file=sys.stderr)
            continue
        calls += cell["items"]
        produced.append(result["run_dir"])
        print(
            f"{prefix}: {result['run_id']} -> {result['run_dir']} "
            f"(running total {calls}/{projected['remaining_calls']} call(s))"
        )

    print(f"\nproduced {len(produced)} run director(ies):")
    for path in produced:
        print(f"  {path}")
    print(f"skipped {projected['finished_cells']} finished cell(s), {calls} generation call(s)")
    if failures:
        for failure in failures:
            print(f"FAILED {failure}", file=sys.stderr)
        print(f"{len(failures)} cell(s) failed; re-run the grid to resume", file=sys.stderr)
        return 1
    return 0


# ---- check: the matrix is declared correctly -------------------------------


def depth_of(cfg: config_mod.Config) -> int:
    """Candidates surviving the last retrieval stage (ADR-0011).

    Dense and hybrid hand k chunks on; rerank hands on `rerank_top` rescored
    ones, which is why that number and not k is the depth to compare.
    """
    if cfg["retrieval.mode"] == "rerank":
        return int(cfg["retrieval.rerank_top"])
    return int(cfg["retrieval.k"])


def config_files(paths: Optional[Sequence[str]] = None) -> List[str]:
    """Resolve config files or directories to a sorted list of YAML paths."""
    files: List[str] = []
    for path in list(paths or [DEFAULT_OUT_DIR]):
        if os.path.isdir(path):
            files.extend(
                os.path.join(path, name)
                for name in sorted(os.listdir(path))
                if name.endswith(".yaml")
            )
        elif os.path.isfile(path):
            files.append(path)
        else:
            raise GridError(f"no such configuration or directory: {path}")
    return files


def _cell_of(path: str) -> str:
    return os.path.basename(path)[: -len(".yaml")]


def check(paths: Optional[Sequence[str]] = None) -> int:
    """Load every emitted config through the closed schema and print the table.

    Nothing is run and nothing is spent: this is the gate before `grid run`, and
    it fails on an unknown key, a missing required value, a duplicated cell, a
    depth below k, or a manifest that disagrees with the files beside it.
    """
    problems: List[str] = []
    rows: List[Dict[str, Any]] = []
    seen: Dict[tuple, str] = {}

    try:
        files = config_files(paths)
    except GridError as error:
        print(f"PROBLEM {error}", file=sys.stderr)
        return 1
    if not files:
        print("PROBLEM no configuration files found", file=sys.stderr)
        return 1

    for path in files:
        cell = _cell_of(path)
        try:
            cfg = config_mod.load(path)
        except config_mod.ConfigError as error:
            problems.append(str(error))
            continue
        factors = (
            cfg["chunk.strategy"],
            cfg["retrieval.mode"],
            cfg["context.mode"],
        )
        if factors in seen:
            problems.append(
                f"{cell}: duplicates the factors of {seen[factors]} "
                f"{list(factors)} -- one cell per design point"
            )
        seen[factors] = cell
        depth = depth_of(cfg)
        k = int(cfg["retrieval.k"])
        if depth < k:
            problems.append(
                f"{cell}: ADR-0011 violation: {depth} candidates reach the metric "
                f"but recall@{k} is computed on them"
            )
        rows.append(
            {
                "cell": cell,
                "chunk": cfg["chunk.strategy"],
                "retrieval": cfg["retrieval.mode"],
                "context": cfg["context.mode"],
                "k": k,
                "depth": depth,
                "threshold": cfg["generate.abstain_score_threshold"],
                "golden": cfg["golden.items_path"],
            }
        )

    problems.extend(_manifest_problems(paths))

    header = "{:<46} {:<22} {:<9} {:<20} {:>3} {:>5} {:>9}  {}"
    print(
        header.format(
            "cell", "chunk", "retrieval", "context", "k", "depth", "abstain", "golden"
        )
    )
    for row in rows:
        print(
            header.format(
                row["cell"],
                row["chunk"],
                row["retrieval"],
                row["context"],
                row["k"],
                row["depth"],
                row["threshold"],
                row["golden"],
            )
        )
    print(f"{len(rows)} cell(s) loaded")

    if problems:
        for problem in problems:
            print(f"PROBLEM {problem}", file=sys.stderr)
        print(f"{len(problems)} problem(s) in the grid", file=sys.stderr)
        return 1
    return 0


def _manifest_problems(paths: Sequence[str]) -> List[str]:
    """A manifest is the join key `aggregate` uses; drift there is a grid bug.

    Two things are compared, because they fail differently. Cell *names* catch a
    manifest and a directory that have diverged in composition. Config *digests*
    catch the quieter case: the same eighteen files, one of them edited, so the
    manifest still names a run id that no run of this configuration will ever have.
    Comparing names alone let that through, and `aggregate` would then report a cell
    as absent while its finished run sat in the run root under a digest nobody
    matched.
    """
    problems: List[str] = []
    for path in list(paths):
        if not os.path.isdir(path):
            continue
        manifest = read_manifest(path)
        if manifest is None:
            continue
        entries = list(manifest.get("cells", []))
        declared = sorted(entry["cell"] for entry in entries)
        materialised = sorted(
            name[: -len(".yaml")] for name in os.listdir(path) if name.startswith("cell-")
        )
        if declared != materialised:
            problems.append(
                f"{path}: {MANIFEST_NAME} declares {len(declared)} cell(s) but "
                f"{len(materialised)} config file(s) are present -- re-run `grid emit`"
            )
            continue
        stored = {entry.get("cell"): str(entry.get("config_digest") or "") for entry in entries}
        for name in materialised:
            try:
                cfg = config_mod.load(os.path.join(path, name + ".yaml"))
            except config_mod.ConfigError:
                # `check` already reports the file itself; a digest for a config that
                # does not load would only be noise.
                continue
            actual = config_digest(cfg)
            expected = stored.get(name, "")
            if expected != actual:
                problems.append(
                    f"{path}: {name} resolves to {actual} but {MANIFEST_NAME} records "
                    f"{expected or '(none)'} -- the configuration changed after the "
                    "manifest was written, so a finished run of this cell could no "
                    "longer be joined; re-run `grid emit`"
                )
    return problems

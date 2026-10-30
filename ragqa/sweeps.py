"""Sensitivity sweeps: three dose-response curves, declared as configuration.

Ticket 13 asks for three curves, and each one is a one-parameter family measured
around the same operating point:

    k      retrieval.k      5, 10, 20, 40     (rerank_top = max(k, 12), ADR-0011)
    chunk  chunk.size       256, 512, 1024    (overlap and parent_size proportional)
    hops   retrieval.hops   1, 2, 3           (the bounded agentic loop)

Every point is a configuration file, and each file differs from the *sweep base*
in exactly the parameter its family sweeps (ADR-0003: an ablation is a config
diff, not a branch). The sweep base is the reference cell
`configs/grid/cell-recursive_parent_child-rerank-plain.yaml` plus one design-wide
change: `golden.limit: 40`, because spec.md's rows 2-4 measure every sweep over the
40 answerable items of golden v1 rather than the full 60-item set. That limit is
the same in all ten cells, so it can never explain a difference between two of
them, and `check` verifies the selected items really are the answerable ones.

Three inherited rules this module enforces rather than documents:

- **ADR-0011, candidate depth versus k.** A reranked cell hands `rerank_top`
  candidates to a metric that computes recall@k. At k = 20 and k = 40 the
  reference's depth of 12 would delete headroom the parameter never intended to
  touch, so the k cells carry `rerank_top = max(k, 12)` and `check` fails loudly
  when a hand-edited file breaks that.
- **ADR-0016, the hop trigger reads `score`, not `fusion_score`.** The trigger is
  on the retrieval mode's own scale, so the number below is a cross-encoder score
  and the hop curve compares like with like.
- **ADR-0012, determinism through the cache.** The cells keep temperature 0 and
  the cached LLM path; the hop cells add exactly one cheap mechanical call per
  round, cached by (model, prompt hash, params).

The hop trigger, in arithmetic
------------------------------
The trigger is the rerank abstention working point of the same golden set: raw
0.426134, the chosen threshold in `reports/abstention/working-points.json` (mode
`rerank`, 40 answerable + 20 near-miss items of golden v1). That is the right
number for a hop trigger because it is the exact point at which the system would
otherwise give up: a round whose best score sits below it is a round whose evidence
the calibration says is not sufficient, which is precisely the round worth spending
one rewrite on.

An earlier version of this note derived the trigger from the grid *floor* of the v0
curve (raw 0.5771, 0.182 below that curve's working point) and, when the sweep
moved to golden v1, the trigger ended up above the abstention point it was meant to
precede. It is now the abstention point itself, on the same score scale, and
`HOP_TRIGGER_SOURCE` records where it came from so a later sweep move is visible
rather than silent.

Consequences worth stating in the report:

- a rewrite is spent exactly on the rounds the system would abstain on, never on a
  round it would have answered, so ?Recall is attributable to the loop rather than
  to a threshold change;
- a rewrite stops as soon as a fused round clears 0.426134 (ADR-0016 keeps each
  hit's own score). A rewritten round that clears it can therefore end above the
  abstention line and turn an abstention into an answer: that is the mechanism
  working, and `hop_stats.json`'s stop reason records which round produced the hit;
- if the loop never fires -- `hit_after_rewrite` zero in the histogram -- the hop
  curve is flat by construction and the honest reading is that the loop does not
  pay for itself on this corpus. `break_even_hop` says so rather than inventing a
  gain.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from . import config as config_mod
from . import grid

# ---- constants ------------------------------------------------------------

REFERENCE_CELL = os.path.join(
    "configs", "grid", "cell-recursive_parent_child-rerank-plain.yaml"
)
DEFAULT_CONFIG_DIR = os.path.join("configs", "sweeps")
DEFAULT_REPORTS_DIR = os.path.join("reports", "sweeps")
DEFAULT_RUNS_ROOT = "runs"

#: The planned size of golden v1 (spec.md row 1 uses the full 60-item set).
PLANNED_ITEMS = 60
#: spec.md rows 2-4: every sweep measures over the 40 answerable items.
ANSWERABLE_ITEMS = 40
ITEM_LIMIT = ANSWERABLE_ITEMS

#: The cheap model the loop rewrites with (PROGRESS.md: gateway facts), the same
#: model the grid's generator uses. The rewrite is mechanical work, so run.py
#: already calls it with `reasoning_effort: "none"` (ADR-0014).
HOP_REWRITE_MODEL = "deepseek-v4.1-flash"

#: The rerank abstention working point of golden v1, in raw cross-encoder score:
#: `reports/abstention/working-points.json`, mode `rerank`, `raw_threshold`. The hop
#: cells fire a rewrite exactly where the system would otherwise abstain, on the
#: same score scale, so the trigger and the decision it precedes cannot disagree.
HOP_TRIGGER = 0.426134

#: Where the trigger came from, recorded so the number stays checkable against the
#: published curve. It is the rerank *working point* (t = 0.2 of the v1 curve), not
#: the grid floor: `working_point_raw` here must equal `HOP_TRIGGER`, and
#: `tests/test_sweeps.py` fails if the published sweep ever moves away from it.
HOP_TRIGGER_SOURCE: Dict[str, Any] = {
    "curve": "reports/abstention/working-points.json, mode rerank, golden v1",
    "population": "40 answerable + 20 near-miss items",
    "working_point_t": 0.2,
    "working_point_raw": 0.426134,
    "rule": "the hop trigger is the abstention working point of the same score "
    "scale and the same golden set: a rewrite is spent exactly on the rounds the "
    "calibration would abstain on",
}

#: spec.md rows 2-4, restated so the projection is checked rather than narrated.
SPEC_INVENTORY = {"k": 160, "chunk": 120, "hops": 120}

#: Every sweep cell keeps the reference's rerank truncation length: it is a property
#: of the embedding/reranker call, not of any swept parameter.
INVARIANTS = {
    "overlap_ratio": 8,  # chunk.overlap * 8 == chunk.size  (64 / 512)
    "parent_ratio": 2,  # chunk.parent_size == 2 * chunk.size  (1024 / 512)
    "k_floor": 12,  # rerank_top == max(k, 12)  (ADR-0011)
}


# ---- the declaration ------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """One point of one curve: a label, the x value it sets, and its config patch."""

    label: str
    value: int
    patch: Dict[str, Any]


@dataclass(frozen=True)
class Family:
    """One dose-response curve: which key moves, and what the points are."""

    name: str
    title: str
    x_key: str
    x_label: str
    #: Keys that may differ between two points of this family. `run.name` is a
    #: derived label and is always allowed; `retrieval.rerank_top` and the chunk
    #: child/parent pair travel with their own parameter because they are its
    #: definition rather than a second knob (ADR-0011; ADR-0010).
    surface: Tuple[str, ...]
    points: Tuple[Point, ...]
    hypothesis: str


def _k_points() -> Tuple[Point, ...]:
    return tuple(
        Point(
            label="k-%02d" % k,
            value=k,
            patch={
                "retrieval.k": k,
                # ADR-0011: never hand a metric fewer candidates than it reads.
                "retrieval.rerank_top": max(k, INVARIANTS["k_floor"]),
            },
        )
        for k in (5, 10, 20, 40)
    )


def _chunk_points() -> Tuple[Point, ...]:
    points = []
    for size in (256, 512, 1024):
        points.append(
            Point(
                label="chunk-%d" % size,
                value=size,
                patch={
                    "chunk.size": size,
                    "chunk.overlap": size // INVARIANTS["overlap_ratio"],
                    "chunk.parent_size": size * INVARIANTS["parent_ratio"],
                },
            )
        )
    return tuple(points)


def _hop_points() -> Tuple[Point, ...]:
    return tuple(
        Point(
            label="hops-%d" % hops,
            value=hops,
            patch={
                "retrieval.hops": hops,
                "retrieval.hop_rewrite_model": HOP_REWRITE_MODEL,
                "retrieval.trigger_threshold": HOP_TRIGGER,
            },
        )
        for hops in (1, 2, 3)
    )


FAMILIES: Tuple[Family, ...] = (
    Family(
        name="k",
        title="retrieval depth",
        x_key="retrieval.k",
        x_label="k",
        surface=("retrieval.k", "retrieval.rerank_top", "run.name"),
        points=_k_points(),
        hypothesis="recall@k rises with depth until the retriever's misses are the "
        "only thing left; past that point the curve is flat and the extra candidates "
        "only cost context tokens, so the depth saturates where recall@k and citation "
        "recall stop moving.",
    ),
    Family(
        name="chunk",
        title="chunk size",
        x_key="chunk.size",
        x_label="chunk size (words)",
        surface=(
            "chunk.size",
            "chunk.overlap",
            "chunk.parent_size",
            "run.name",
        ),
        points=_chunk_points(),
        hypothesis="small chunks sharpen the match but starve the generator of "
        "context, large chunks do the reverse: citation precision peaks before "
        "recall@k does, and the crossing is where the curve saturates.",
    ),
    Family(
        name="hops",
        title="retrieval hops",
        x_key="retrieval.hops",
        x_label="hops",
        surface=("retrieval.hops", "run.name"),
        points=_hop_points(),
        hypothesis="a second round recovers the questions whose first round surfaced "
        "nothing above the trigger; a third round recovers almost none of what the "
        "second did not, while still paying a rewrite call and an extra retrieval.",
    ),
)


def family(name: str) -> Family:
    for entry in FAMILIES:
        if entry.name == name:
            return entry
    raise SweepError(
        "unknown sweep family %r; declared families are %s"
        % (name, [entry.name for entry in FAMILIES])
    )


def _point(name: str) -> Tuple[Family, Point]:
    for entry in FAMILIES:
        for point in entry.points:
            if point.label == name:
                return entry, point
    raise SweepError(
        "unknown sweep point %r; declared points are %s"
        % (name, [point.label for entry in FAMILIES for point in entry.points])
    )


class SweepError(RuntimeError):
    """A defect in the sweep declaration or a file that drifted from it."""


# ---- baseline -> cells ----------------------------------------------------


_REFERENCE: Optional[Dict[str, Any]] = None


def reference_values() -> Dict[str, Any]:
    """The sweep base, flat: the reference cell's resolved values + the item limit.

    Resolved rather than raw so that two cells can be compared key by key without
    any default quietly standing in for a value neither file mentions.
    """
    global _REFERENCE
    if _REFERENCE is None:
        values = config_mod.load(REFERENCE_CELL).as_dict()
        values["golden.limit"] = ITEM_LIMIT
        _REFERENCE = values
    return dict(_REFERENCE)


def _config_for(label: str, patch: Dict[str, Any]) -> config_mod.Config:
    values = reference_values()
    values.update(patch)
    values["run.name"] = "sweep-" + label
    return config_mod.Config(values)


def cells() -> List[Dict[str, Any]]:
    """Every declared sweep cell, in run order."""
    out: List[Dict[str, Any]] = []
    for entry in FAMILIES:
        for point in entry.points:
            cfg = _config_for(point.label, point.patch)
            out.append(
                {
                    "label": point.label,
                    "family": entry.name,
                    "title": entry.title,
                    "x_key": entry.x_key,
                    "x": point.value,
                    "patch": dict(point.patch),
                    "config": cfg,
                    "config_path": os.path.join(DEFAULT_CONFIG_DIR, point.label + ".yaml"),
                    "run_name": cfg["run.name"],
                    "digest": grid.config_digest(cfg),
                    "items": expected_items(cfg),
                    "hops": int(cfg["retrieval.hops"]),
                    "depth": grid.depth_of(cfg),
                    "trigger": cfg["retrieval.trigger_threshold"],
                }
            )
    return out


def cell(label: str) -> Dict[str, Any]:
    for entry in cells():
        if entry["label"] == label:
            return entry
    raise SweepError("unknown sweep cell %r" % (label,))


def expected_items(cfg: config_mod.Config) -> int:
    """How many golden items this cell will generate for.

    Same rule as the grid's projection: an explicit `golden.limit` wins, the file's
    own length is used when the golden set exists, and the spec's planned size
    stands in until then -- so a projection is never silently optimistic.
    """
    limit = cfg["golden.limit"]
    path = cfg["golden.items_path"]
    available: Optional[int] = None
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            available = sum(1 for line in handle if line.strip())
    if limit:
        return int(limit) if available is None else min(int(limit), available)
    return available if available is not None else PLANNED_ITEMS


# ---- emit -----------------------------------------------------------------


def _diff_keys(left: Dict[str, Any], right: Dict[str, Any]) -> set:
    return {key for key in left if left[key] != right[key]}


def _render(entry: Dict[str, Any], base: Dict[str, Any]) -> str:
    cfg = entry["config"]
    differing = sorted(_diff_keys(cfg.as_dict(), base) - {"run.name"})
    header = [
        "# %s -- the %s sweep (ticket 13). Generated by `python -m ragqa sweep emit`"
        % (entry["label"], entry["title"]),
        "# or `python scripts/run_sweeps.py --emit`; edit `ragqa/sweeps.py`, never this file.",
        "#",
        "#   sweep base: configs/grid/cell-recursive_parent_child-rerank-plain.yaml",
        "#               (recursive_parent_child / rerank / plain) + golden.limit 40",
        "#   point     : %s = %s" % (entry["x_key"], entry["x"]),
        "#   differs   : %s" % (", ".join(differing) if differing else "(nothing: this is the base point)"),
        "#   invariants: rerank_top = max(k, 12) (ADR-0011); same corpus, same golden",
        "#               set, same prices as the reference cell.",
    ]
    if entry["family"] == "hops":
        header += [
            "#",
            "#   trigger   : retrieval.trigger_threshold = %s, the rerank abstention"
            % HOP_TRIGGER,
            "#               working point of golden v1 (reports/abstention/",
            "#               working-points.json), so a rewrite fires exactly where the",
            "#               system would otherwise abstain. Identical in hops-1,",
            "#               hops-2 and hops-3 so only the cap differs.",
        ]
    if cfg["chunk.overlap"] * INVARIANTS["overlap_ratio"] != cfg["chunk.size"]:
        header.append("#   WARNING: overlap is not size/8 -- the chunk sweep is confounded")
    body = yaml.safe_dump(cfg.nested(), sort_keys=True, default_flow_style=False, width=100)
    return "\n".join(header) + "\n" + body


def emit(out_dir: Optional[str] = None) -> List[str]:
    """Write one YAML per declared cell; a pure function of the declaration."""
    directory = out_dir or DEFAULT_CONFIG_DIR
    os.makedirs(directory, exist_ok=True)
    base = reference_values()
    written: List[str] = []
    for entry in cells():
        path = os.path.join(directory, entry["label"] + ".yaml")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_render(entry, base))
        written.append(path)
    # The directory *is* the declaration: a leftover point from an earlier
    # declaration would silently re-enter `check` and later `curve`.
    keep = {os.path.basename(path) for path in written}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".yaml") and name not in keep:
            os.remove(os.path.join(directory, name))
    return written


# ---- check ----------------------------------------------------------------


def _golden_problems(label: str, cfg: config_mod.Config) -> List[str]:
    """The 40 items must be the 40 *answerable* ones, not the first 40 lines of anything."""
    path = cfg["golden.items_path"]
    limit = cfg["golden.limit"]
    if not (path and limit and os.path.isfile(path)):
        return []
    problems: List[str] = []
    answerable = 0
    seen = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or seen >= int(limit):
                continue
            seen += 1
            item = json.loads(line)
            if bool(item.get("answerable", True)):
                answerable += 1
    if answerable != seen:
        problems.append(
            "%s: golden.limit=%s selects %d item(s) of which only %d are answerable; the "
            "sweeps measure over the %d answerable items (spec.md rows 2-4) and the golden "
            "set must list answerable items first"
            % (label, limit, seen, answerable, ANSWERABLE_ITEMS)
        )
    return problems


def _family_problems(entry: Dict[str, Any], cfg: config_mod.Config) -> List[str]:
    problems: List[str] = []
    label = entry["label"]
    if entry["family"] == "k":
        k = int(cfg["retrieval.k"])
        if int(cfg["retrieval.rerank_top"]) != max(k, INVARIANTS["k_floor"]):
            problems.append(
                "%s: rerank_top is %s but this sweep point declares max(k, %d) = %d"
                % (label, cfg["retrieval.rerank_top"], INVARIANTS["k_floor"],
                   max(k, INVARIANTS["k_floor"]))
            )
    elif entry["family"] == "chunk":
        size = int(cfg["chunk.size"])
        if int(cfg["chunk.overlap"]) * INVARIANTS["overlap_ratio"] != size:
            problems.append(
                "%s: overlap %s / size %s is not the reference ratio 1/%d -- the chunk "
                "sweep would move two parameters at once"
                % (label, cfg["chunk.overlap"], size, INVARIANTS["overlap_ratio"])
            )
        if int(cfg["chunk.parent_size"]) != size * INVARIANTS["parent_ratio"]:
            problems.append(
                "%s: parent_size %s is not %dx size %s -- the parent budget must scale "
                "with the child budget"
                % (label, cfg["chunk.parent_size"], INVARIANTS["parent_ratio"], size)
            )
    elif entry["family"] == "hops":
        if not cfg["retrieval.hop_rewrite_model"]:
            problems.append(
                "%s: retrieval.hop_rewrite_model is empty, so the loop has nothing to "
                "rewrite with and hops > 1 would silently fall back to the generator" % label
            )
        if cfg["retrieval.trigger_threshold"] is None:
            problems.append(
                "%s: retrieval.trigger_threshold is unset; the trigger would fall back to "
                "the generator's abstention threshold, which is the wrong decision point" % label
            )
    return problems


def _one_parameter_problems(loaded: Dict[str, config_mod.Config]) -> List[str]:
    """Every family's cells differ, pairwise, only inside that family's surface."""
    problems: List[str] = []
    for entry in FAMILIES:
        labels = [point.label for point in entry.points if point.label in loaded]
        allowed = set(entry.surface)
        for index, left in enumerate(labels):
            for right in labels[index + 1:]:
                differing = _diff_keys(loaded[left].as_dict(), loaded[right].as_dict())
                extra = differing - allowed
                if extra:
                    problems.append(
                        "%s vs %s: differ in %s as well as the swept parameter %s -- two "
                        "variables, one number (ADR-0003)"
                        % (left, right, ", ".join(sorted(extra)), entry.x_key)
                    )
    return problems


def check(paths: Optional[Sequence[str]] = None) -> int:
    """Load every emitted cell through the closed schema and verify the declaration.

    Fails on: an unknown config key (config.py), a missing required value, a file no
    sweep declares, a file that drifted from its declaration in any key, a candidate
    depth below k (ADR-0011), a chunk ratio that no longer matches the reference, a
    hop cell without a trigger or a rewrite model, or an item limit that is not the
    answerable subset. Nothing is run and nothing is spent.
    """
    problems: List[str] = []
    rows: List[Dict[str, Any]] = []
    declared = {entry["label"]: entry for entry in cells()}

    try:
        files = grid.config_files(paths or [DEFAULT_CONFIG_DIR])
    except grid.GridError as error:
        print("PROBLEM %s" % error, file=sys.stderr)
        return 1
    if not files:
        print("PROBLEM no configuration files found", file=sys.stderr)
        return 1

    loaded: Dict[str, config_mod.Config] = {}
    base = reference_values()
    for path in files:
        label = os.path.basename(path)[: -len(".yaml")]
        try:
            cfg = config_mod.load(path)
        except config_mod.ConfigError as error:
            problems.append(str(error))
            continue
        entry = declared.get(label)
        if entry is None:
            problems.append(
                "%s: no sweep declares this point; declared points are %s"
                % (label, ", ".join(sorted(declared)))
            )
            continue
        loaded[label] = cfg
        values = cfg.as_dict()
        expected = {
            key for key, value in entry["patch"].items() if base.get(key) != value
        } | {"run.name"}
        drift = _diff_keys(values, base) - expected
        if drift:
            problems.append(
                "%s: differs from the sweep base in %s, which this point does not sweep "
                "(%s) -- re-emit rather than hand-edit"
                % (label, ", ".join(sorted(drift)), entry["x_key"])
            )
        missing = expected - _diff_keys(values, base)
        if missing:
            problems.append(
                "%s: does not set %s, so the file is not the point it claims to be"
                % (label, ", ".join(sorted(missing)))
            )
        depth = grid.depth_of(cfg)
        k = int(cfg["retrieval.k"])
        if depth < k:
            problems.append(
                "%s: ADR-0011 violation: %d candidates reach the metric but recall@%d is "
                "computed on them" % (label, depth, k)
            )
        problems.extend(_family_problems(entry, cfg))
        problems.extend(_golden_problems(label, cfg))
        rows.append(
            {
                "label": label,
                "family": entry["family"],
                "x": entry["x"],
                "k": k,
                "depth": depth,
                "items": expected_items(cfg),
                "trigger": cfg["retrieval.trigger_threshold"],
                "hops": int(cfg["retrieval.hops"]),
            }
        )

    problems.extend(_one_parameter_problems(loaded))

    header = "{:<11} {:<7} {:>6} {:>4} {:>6} {:>6} {:>10} {:>5}"
    print(header.format("cell", "family", "x", "k", "depth", "items", "trigger", "hops"))
    for row in rows:
        print(
            header.format(
                row["label"],
                row["family"],
                row["x"],
                row["k"],
                row["depth"],
                row["items"],
                "-" if row["trigger"] is None else "%.4f" % float(row["trigger"]),
                row["hops"],
            )
        )
    print("%d cell(s) loaded" % len(rows))

    if problems:
        for problem in problems:
            print("PROBLEM %s" % problem, file=sys.stderr)
        print("%d problem(s) in the sweep set" % len(problems), file=sys.stderr)
        return 1
    return 0


# ---- run: resume, project, execute ----------------------------------------


def plan(
    paths: Optional[Sequence[str]] = None,
    out_root: Optional[str] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """The run order, with each point marked finished or pending.

    Finished means "a run directory with metrics.json already exists for this exact
    resolved configuration" (grid.finished_runs matches on the config digest), so an
    interrupted sweep resumes instead of re-spending on points that already ran.
    """
    files = grid.config_files(paths or [DEFAULT_CONFIG_DIR])
    by_label = {os.path.basename(path)[: -len(".yaml")]: path for path in files}
    entries: List[Dict[str, Any]] = []
    for entry in cells():
        path = by_label.get(entry["label"])
        cell_entry = dict(entry)
        cell_entry["config_path"] = path or entry["config_path"]
        cell_entry["out_root"] = out_root or entry["config"]["run.out_root"]
        if path:
            # The file is the configuration of record; the declared digest is what
            # `read_curve` looks a run up by, so a drifted file is a hard stop rather
            # than a silently different experiment.
            on_disk = config_mod.load(path)
            if grid.config_digest(on_disk) != entry["digest"]:
                cell_entry["status"] = "drifted"
            else:
                cell_entry["status"] = "pending"
                cell_entry["config"] = on_disk
                cell_entry["items"] = expected_items(on_disk)
        else:
            cell_entry["status"] = "not-emitted"
        cell_entry["run_dir"] = ""
        entries.append(cell_entry)

    if not force:
        index = grid.finished_runs({entry["out_root"] for entry in entries})
        for entry in entries:
            if entry["status"] in ("drifted", "not-emitted"):
                continue
            found = index.get(entry["digest"])
            if found:
                entry["status"] = "finished"
                entry["run_dir"] = found
            else:
                entry["status"] = "pending"
    else:
        for entry in entries:
            if entry["status"] not in ("drifted", "not-emitted"):
                entry["status"] = "pending"
    return entries


def projection(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The sweep design's generation calls, and what is left of them.

    A generation call is one golden item of one cell. The rewrite calls the loop can
    add are counted separately and as a *worst case* -- every question would have to
    run its full hop budget -- because the real number is only known from
    `hop_stats.json` after the run.
    """
    by_family: Dict[str, int] = {}
    items_by_cell: Dict[str, int] = {}
    calls = 0
    rewrites = 0
    remaining = 0
    remaining_rewrites = 0
    for entry in entries:
        items = int(entry["items"])
        items_by_cell[entry["label"]] = items
        by_family[entry["family"]] = by_family.get(entry["family"], 0) + items
        calls += items
        extra = items * (int(entry["hops"]) - 1)
        rewrites += extra
        if entry["status"] != "finished":
            remaining += items
            remaining_rewrites += extra
    return {
        "cells": len(entries),
        "items_by_cell": items_by_cell,
        "by_family": by_family,
        "generation_calls": calls,
        "rewrite_calls": rewrites,
        "finished_cells": sum(1 for entry in entries if entry["status"] == "finished"),
        "remaining_calls": remaining,
        "remaining_rewrite_calls": remaining_rewrites,
    }


def compare_projection(
    report: Dict[str, Any], inventory: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """Compare each family's projected generations against spec.md rows 2-4."""
    expected = inventory or SPEC_INVENTORY
    deltas = {
        name: report["by_family"].get(name, 0) - count
        for name, count in expected.items()
    }
    return {"ok": all(delta == 0 for delta in deltas.values()), "deltas": deltas}


def _execute_cell(entry: Dict[str, Any], out_root: str) -> Dict[str, Any]:
    """Run one sweep point; imported lazily so a dry run touches no model, no GPU."""
    from . import run as run_mod

    return run_mod.execute(entry["config"], out_root)


def run(
    paths: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    force: bool = False,
    out_root: Optional[str] = None,
) -> int:
    """Execute pending points in declaration order; report what was produced."""
    try:
        entries = plan(paths, out_root=out_root, force=force)
    except grid.GridError as error:
        print("PROBLEM %s" % error, file=sys.stderr)
        return 1
    missing = [entry["label"] for entry in entries if entry["status"] == "not-emitted"]
    if missing:
        print(
            "PROBLEM cell(s) %s have no configuration file under %s; run `emit` first"
            % (", ".join(missing), (paths or [DEFAULT_CONFIG_DIR])[0]),
            file=sys.stderr,
        )
        return 1
    drifted = [entry["label"] for entry in entries if entry["status"] == "drifted"]
    if drifted:
        print(
            "PROBLEM cell(s) %s on disk no longer match the sweep declaration; run "
            "`check` and re-emit rather than spending money on a file that is not the "
            "point it claims to be" % ", ".join(drifted),
            file=sys.stderr,
        )
        return 1

    report = projection(entries)
    width = max(len(entry["label"]) for entry in entries)
    print(
        "sweeps: %d cell(s) in %d famil(ies), %d generation call(s) for the design, "
        "%d remaining"
        % (
            report["cells"],
            len({entry["family"] for entry in entries}),
            report["generation_calls"],
            report["remaining_calls"],
        )
    )
    for position, entry in enumerate(entries, 1):
        print(
            "{:>2}. {:<{width}}  {:<9}  {:>3} item(s)  {:>3} call(s)  {}".format(
                position,
                entry["label"],
                entry["status"],
                entry["items"],
                entry["items"],
                entry["run_dir"] or entry["run_name"] + "-*",
                width=width,
            )
        )
    print(
        "projection: %s generation call(s) (%s) vs spec.md rows 2-4 (%s)"
        % (
            report["generation_calls"],
            ", ".join(
                "%s %d" % (name, count) for name, count in sorted(report["by_family"].items())
            ),
            ", ".join(
                "%s %d" % (name, count) for name, count in sorted(SPEC_INVENTORY.items())
            ),
        )
    )
    comparison = compare_projection(report)
    if not comparison["ok"]:
        print(
            "PROBLEM projection disagrees with the inventory by %s -- fix the declaration, "
            "do not spend money on it" % comparison["deltas"],
            file=sys.stderr,
        )
        return 1
    print(
        "rewrites: worst case %d call(s) on top (%s); the real number comes from "
        "hop_stats.json"
        % (
            report["rewrite_calls"],
            ", ".join(
                "%s %d"
                % (entry["label"], entry["items"] * (int(entry["hops"]) - 1))
                for entry in entries
                if int(entry["hops"]) > 1
            )
            or "none",
        )
    )

    if dry_run:
        print("dry run: nothing executed, nothing spent")
        return 0

    produced: List[str] = []
    failures: List[str] = []
    calls = 0
    for position, entry in enumerate(entries, 1):
        prefix = "[%d/%d] %s" % (position, len(entries), entry["label"])
        if entry["status"] == "finished":
            print("%s: finished at %s, skipped" % (prefix, entry["run_dir"]))
            continue
        try:
            result = _execute_cell(entry, entry["out_root"])
        except Exception as error:  # one dead point must not stop the sweep
            failures.append("%s: %s" % (entry["label"], error))
            print("%s: FAILED (%s)" % (prefix, error), file=sys.stderr)
            continue
        calls += entry["items"]
        produced.append(result["run_dir"])
        print(
            "%s: %s -> %s (running total %d/%d call(s))"
            % (prefix, result["run_id"], result["run_dir"], calls, report["remaining_calls"])
        )

    print("\nproduced %d run director(ies):" % len(produced))
    for path in produced:
        print("  %s" % path)
    print(
        "skipped %d finished point(s), %d generation call(s)"
        % (report["finished_cells"], calls)
    )
    if failures:
        for failure in failures:
            print("FAILED %s" % failure, file=sys.stderr)
        print("%d point(s) failed; re-run to resume" % len(failures), file=sys.stderr)
        return 1
    return 0


# ---- the curve reader -----------------------------------------------------

CURVE_COLUMNS: Tuple[str, ...] = (
    "label",
    "family",
    "x",
    "status",
    "run_id",
    "recall_at_k",
    "mrr",
    "ndcg_at_10",
    "citation_precision",
    "citation_recall",
    "span_hit_rate",
    "over_abstain_rate",
    "p50_ms",
    "p95_ms",
    "tokens",
    "cny_per_1k",
    "answers",
    "hops",
    "mean_hops",
    "stop_hit_first_round",
    "stop_hit_after_rewrite",
    "stop_cap_reached",
    "stop_abstained",
    "delta_recall",
    "delta_citation_precision",
    "delta_p50_ms",
    "delta_cny_per_1k",
    "incremental_cny_per_recall_point",
)

#: The hop fields that only a hop cell has; a k or chunk row leaves them blank.
HOP_FIELDS = (
    "mean_hops",
    "stop_hit_first_round",
    "stop_hit_after_rewrite",
    "stop_cap_reached",
    "stop_abstained",
)

_RATIO_FIELDS = (
    "recall_at_k",
    "mrr",
    "ndcg_at_10",
    "citation_precision",
    "citation_recall",
    "span_hit_rate",
    "over_abstain_rate",
)

_MS_FIELDS = ("p50_ms", "p95_ms")


def _read_json(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _tokens(metrics: Dict[str, Any], cache_stats: Dict[str, Any]) -> Optional[int]:
    components = ((metrics.get("system") or {}).get("cost_components") or {})
    if components:
        return int(
            sum(
                int(value.get("tokens_in", 0) or 0) + int(value.get("tokens_out", 0) or 0)
                for value in components.values()
                if isinstance(value, dict)
            )
        )
    if cache_stats:
        return int(cache_stats.get("llm_tokens_in", 0) or 0) + int(
            cache_stats.get("llm_tokens_out", 0) or 0
        )
    return None


def _row_for(entry: Dict[str, Any], run_dir: str) -> Dict[str, Any]:
    """One curve point, read from a finished run directory. Never guessed."""
    row: Dict[str, Any] = {column: None for column in CURVE_COLUMNS}
    row.update(
        {
            "label": entry["label"],
            "family": entry["family"],
            "x": entry["x"],
            "hops": entry["hops"],
            "run_id": "",
        }
    )
    if not run_dir:
        row["status"] = "pending"
        return row

    metrics = _read_json(os.path.join(run_dir, "metrics.json"))
    retrieval = metrics.get("retrieval") or {}
    citations = metrics.get("citations") or {}
    abstention = metrics.get("abstention") or {}
    system = metrics.get("system") or {}
    timings = _read_json(os.path.join(run_dir, "timings.json"))
    hop_stats = _read_json(os.path.join(run_dir, "hop_stats.json"))
    cache_stats = _read_json(os.path.join(run_dir, "cache_stats.json"))

    row.update(
        {
            "status": "finished",
            "run_id": os.path.basename(run_dir),
            "recall_at_k": retrieval.get("recall_at_k", retrieval.get("hit_rate")),
            "mrr": retrieval.get("mrr"),
            "ndcg_at_10": retrieval.get("ndcg_at_10"),
            "citation_precision": citations.get("citation_precision"),
            "citation_recall": citations.get("citation_recall"),
            "span_hit_rate": citations.get("span_hit_rate"),
            "over_abstain_rate": abstention.get("over_abstain_rate"),
            "p50_ms": timings.get("p50_ms"),
            "p95_ms": timings.get("p95_ms"),
            "tokens": _tokens(metrics, cache_stats),
            "cny_per_1k": system.get("cost_per_1k_questions_cny"),
            "answers": (metrics.get("items") or {}).get("answerable"),
        }
    )
    if entry["family"] == "hops":
        stops = hop_stats.get("stop_reasons") or {}
        row.update(
            {
                "mean_hops": hop_stats.get("mean_hops"),
                "stop_hit_first_round": stops.get("hit_first_round", 0),
                "stop_hit_after_rewrite": stops.get("hit_after_rewrite", 0),
                "stop_cap_reached": stops.get("cap_reached", 0),
                "stop_abstained": stops.get("abstained", 0),
            }
        )
    return row


def _number(value: Any, digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _anchor(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The point a hop curve is measured against: hops = 1, when it has a run."""
    for row in rows:
        if int(row["hops"]) == 1:
            return row if row["status"] == "finished" else None
    return None


def _attach_deltas(rows: List[Dict[str, Any]], anchor: Optional[Dict[str, Any]]) -> None:
    """Δ against hops = 1, plus the marginal ¥ per recall point.

    The marginal number is what the report needs: a hop that buys recall points at a
    higher marginal price than the previous hop has stopped paying for itself.
    """
    for row in rows:
        if row["family"] != "hops":
            continue
        if row["status"] != "finished" or anchor is None:
            row["delta_recall"] = None
            row["delta_citation_precision"] = None
            row["delta_p50_ms"] = None
            row["delta_cny_per_1k"] = None
            row["incremental_cny_per_recall_point"] = None
            continue
        row["delta_recall"] = _number(
            (row["recall_at_k"] or 0.0) - (anchor["recall_at_k"] or 0.0)
        )
        row["delta_citation_precision"] = _number(
            (row["citation_precision"] or 0.0) - (anchor["citation_precision"] or 0.0)
        )
        row["delta_p50_ms"] = _number((row["p50_ms"] or 0.0) - (anchor["p50_ms"] or 0.0), 3)
        row["delta_cny_per_1k"] = _number(
            (row["cny_per_1k"] or 0.0) - (anchor["cny_per_1k"] or 0.0)
        )

    previous = anchor
    for row in rows:
        if row["family"] != "hops" or row["status"] != "finished" or previous is None:
            continue
        gained = (row["recall_at_k"] or 0.0) - (previous["recall_at_k"] or 0.0)
        spent = (row["cny_per_1k"] or 0.0) - (previous["cny_per_1k"] or 0.0)
        row["incremental_cny_per_recall_point"] = (
            _number(spent / gained) if gained > 1e-9 else None
        )
        previous = row


def read_curve(
    name: str, runs_root: str = DEFAULT_RUNS_ROOT
) -> List[Dict[str, Any]]:
    """One row per declared point of a family, finished or pending.

    The run directory is looked up by the point's configuration digest, which is the
    identity `run.py` stamps into every run directory: a point that never ran has no
    digest on disk and is reported pending rather than filled with a guess.
    """
    entry = family(name)
    index = grid.finished_runs([runs_root])
    rows = []
    for point in entry.points:
        declared = cell(point.label)
        rows.append(_row_for(declared, index.get(declared["digest"], "")))
    _attach_deltas(rows, _anchor(rows))
    return rows


def break_even_hop(rows: Sequence[Dict[str, Any]]) -> Optional[int]:
    """The last hop that still pays for itself, by its own marginal arithmetic.

    Hop h pays when it buys recall points more cheaply than hop h-1 did. The first
    hop whose marginal ¥ per recall point is at least the previous hop's marginal
    price (or which buys no recall at all) is where the loop stops paying, and the
    answer to "at which hop" is h - 1. `None` means the curve is not measurable yet.
    """
    anchor = _anchor(rows)
    if anchor is None:
        return None
    previous_price: Optional[float] = None
    last_paying = 1
    for row in sorted(
        (row for row in rows if row["status"] == "finished"), key=lambda row: int(row["hops"])
    ):
        if int(row["hops"]) == 1:
            continue
        gained = (row["recall_at_k"] or 0.0) - (anchor["recall_at_k"] or 0.0)
        price = row["incremental_cny_per_recall_point"]
        if price is None or gained <= 1e-9:
            return last_paying
        if previous_price is not None and price >= previous_price:
            return int(row["hops"]) - 1
        previous_price = price
        last_paying = int(row["hops"])
    return last_paying


# ---- artifacts ------------------------------------------------------------


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _write_csv(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CURVE_COLUMNS)
        for row in rows:
            writer.writerow([_cell_text(row[column]) for column in CURVE_COLUMNS])


def _md_cell(value: Any) -> str:
    if value is None:
        return "pending"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _md_header(entry: Family, rows: Sequence[Dict[str, Any]], runs_root: str) -> List[str]:
    finished = [row for row in rows if row["status"] == "finished"]
    lines = [
        "# %s sweep — %s" % (entry.name, entry.title),
        "",
        "| | |",
        "|---|---|",
        "| family | `%s` |" % entry.name,
        "| swept key | `%s` |" % entry.x_key,
        "| points | %s |" % ", ".join(str(point.value) for point in entry.points),
        "| sweep base | `%s` + `golden.limit: %d` |" % (REFERENCE_CELL.replace("\\", "/"), ITEM_LIMIT),
        "| items per point | %d answerable (spec.md rows 2-4) |" % ANSWERABLE_ITEMS,
        "| runs root | `%s` |" % runs_root.replace("\\", "/"),
        "| finished points | %d of %d |" % (len(finished), len(rows)),
        "",
        "Generated by `python scripts/run_sweeps.py --curve %s` (or "
        "`python -m ragqa sweep curve %s`). Every number below is read out of the run "
        "directory named in the `run_id` column; a point with no finished run is marked "
        "*pending* rather than filled in." % (entry.name, entry.name),
        "",
    ]
    return lines


_MD_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("label", "point"),
    ("run_id", "run id"),
    ("recall_at_k", "recall@k"),
    ("mrr", "MRR"),
    ("ndcg_at_10", "nDCG@10"),
    ("citation_precision", "cite P"),
    ("citation_recall", "cite R"),
    ("span_hit_rate", "span hit"),
    ("over_abstain_rate", "over-abstain"),
    ("p50_ms", "p50 ms"),
    ("p95_ms", "p95 ms"),
    ("tokens", "tokens"),
    ("cny_per_1k", "¥/1k questions"),
)


def _md_table(entry: Family, rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = [
        "| " + " | ".join(title for _, title in _MD_COLUMNS) + " |",
        "|" + "---|" * len(_MD_COLUMNS),
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_md_cell(row[column]) for column, _ in _MD_COLUMNS)
            + " |"
        )
    return lines


def _md_hop_section(rows: Sequence[Dict[str, Any]]) -> List[str]:
    finished = [row for row in rows if row["status"] == "finished"]
    if not finished:
        return [
            "",
            "## The loop's own arithmetic",
            "",
            "Pending: no hop cell has a finished run under this runs root yet, so the "
            "stop-reason histogram, the deltas and the break-even hop cannot be read. "
            "Run the sweeps (`python scripts/run_sweeps.py`) and re-run this command.",
            "",
        ]
    lines = [
        "",
        "## Stop reasons and deltas against hops = 1",
        "",
        "| hops | stop: first round | stop: after rewrite | stop: cap reached | "
        "stop: abstained | mean hops | ΔRecall | Δcite P | Δp50 ms | Δ¥/1k | "
        "marginal ¥ per recall point |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % tuple(
                [_md_cell(row["hops"])]
                + [
                    _md_cell(row[field])
                    for field in (
                        "stop_hit_first_round",
                        "stop_hit_after_rewrite",
                        "stop_cap_reached",
                        "stop_abstained",
                        "mean_hops",
                        "delta_recall",
                        "delta_citation_precision",
                        "delta_p50_ms",
                        "delta_cny_per_1k",
                    )
                ]
                + [_fmt_marginal(row["incremental_cny_per_recall_point"])]
            )
        )
    stops = sum(
        int(row["stop_hit_after_rewrite"] or 0) for row in finished if int(row["hops"]) > 1
    )
    decided = break_even_hop(rows)
    lines += ["", "## At which hop the loop stops paying for itself", ""]
    if decided is None:
        lines.append("Pending: hops = 1 has no finished run to measure against.")
    elif stops == 0:
        lines.append(
            "**Hop 1.** No question finished as `hit_after_rewrite` at hops = 2 or 3, so "
            "the extra rounds bought nothing: the trigger (%s) never fired on a round "
            "that a rewrite could rescue, and every additional hop only paid for itself "
            "in latency and tokens. ΔRecall is 0.0000 at both hops, which makes the "
            "marginal ¥ per recall point undefined — the arithmetic that decides this is "
            "0 recall for a positive price." % ("%.4f" % HOP_TRIGGER)
        )
    else:
        lines.append(
            "**Hop %s.** Read the marginal column: the first hop whose marginal ¥ per "
            "recall point is no lower than the previous hop's is the hop that no longer "
            "pays, so the loop's own break-even point is the hop before it. Recompute "
            "from the CSV if the numbers move; the rule is the column, not this sentence."
            % decided
        )
    lines += [
        "",
        "Arithmetic: marginal price of hop h = (¥/1k at h − ¥/1k at h−1) ÷ "
        "(recall@k at h − recall@k at h−1); the loop stops paying at the first h whose "
        "marginal price is ≥ the marginal price at h−1, or whose recall gain is zero.",
        "",
    ]
    return lines


def _fmt_marginal(value: Any) -> str:
    if value is None:
        return "undefined"
    return "%.1f" % value


def _md_notes(entry: Family, rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = ["", "## Reading this curve", "", "Expectation, stated before the numbers: "
             + entry.hypothesis, ""]
    finished = [row for row in rows if row["status"] == "finished"]
    if len(finished) < len(rows):
        lines += [
            "Saturation cannot be read yet: %d of %d points have a finished run. The "
            "rows above are the declaration, not a measurement, and the missing ones are "
            "marked pending on purpose." % (len(finished), len(rows)),
            "",
            "```",
            "python scripts/run_sweeps.py --emit --check",
            "python scripts/run_sweeps.py            # executes the pending points",
            "python scripts/run_sweeps.py --curve %s" % entry.name,
            "```",
            "",
        ]
    else:
        lines += [
            "Saturation is read off the recall@k and citation-precision columns: the "
            "first point after which neither moves by more than the run-to-run noise "
            "(ADR-0012: a rerun reproduces its metrics through the cache) is where the "
            "swept parameter stops buying anything.",
            "",
        ]
    return lines


def _write_md(path: str, entry: Family, rows: Sequence[Dict[str, Any]], runs_root: str) -> None:
    lines = _md_header(entry, rows, runs_root)
    lines += [""] + _md_table(entry, rows) + [""]
    if entry.name == "hops":
        lines += _md_hop_section(rows)
    lines += _md_notes(entry, rows)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def _plot(path: str, entry: Family, rows: Sequence[Dict[str, Any]]) -> bool:
    """Two panels of the curve, plus the stop histogram for the hop family.

    Returns False when matplotlib is unavailable; the CSV and the table carry the same
    numbers, so a missing figure is a degraded artifact rather than a lost result.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - environment guard
        print(
            "note: matplotlib is unavailable, so %s was not drawn; the CSV and the "
            "markdown table carry the same numbers" % os.path.basename(path),
            file=sys.stderr,
        )
        return False

    finished = [row for row in rows if row["status"] == "finished"]
    if not finished:
        # Nothing is measured yet: a figure of empty axes with a -0.04..0.04 range
        # reads like a broken plot rather than an unmeasured curve.
        figure, axes = plt.subplots(1, 1, figsize=(6.4, 3.6))
        axes.axis("off")
        axes.text(
            0.5,
            0.55,
            "%s sweep: no finished run yet" % entry.name,
            ha="center",
            va="center",
            fontsize=12,
            color="#404040",
        )
        axes.text(
            0.5,
            0.35,
            "points: %s\nrun `python scripts/run_sweeps.py` and re-run this command"
            % ", ".join(str(point.value) for point in entry.points),
            ha="center",
            va="center",
            fontsize=9,
            color="#7f7f7f",
        )
        figure.tight_layout()
        figure.savefig(path, dpi=140)
        plt.close(figure)
        return True

    panels = 3 if entry.name == "hops" else 2
    figure, axes = plt.subplots(1, panels, figsize=(4.2 * panels, 4.2))
    xs = [row["x"] for row in finished]

    left = axes[0]
    for column, label, colour in (
        ("recall_at_k", "recall@k", "#1f4e79"),
        ("citation_precision", "citation precision", "#c00000"),
        ("span_hit_rate", "span hit rate", "#2e75b6"),
    ):
        values = [row[column] for row in finished]
        if any(value is not None for value in values):
            left.plot(xs, [value or 0.0 for value in values], "-o", ms=3.5, lw=1.2,
                      label=label, color=colour)
    left.set_xlabel(entry.x_label)
    left.set_ylabel("rate")
    left.set_title("%s: quality" % entry.name, fontsize=10)
    left.set_ylim(-0.02, 1.05)
    left.set_xticks(xs)
    left.grid(alpha=0.3)
    if left.get_lines():
        left.legend(fontsize=8)

    right = axes[1]
    cost = [row["cny_per_1k"] or 0.0 for row in finished]
    right.plot(xs, cost, "-o", ms=3.5, lw=1.2, color="#548235", label="¥ per 1,000 questions")
    right.set_xlabel(entry.x_label)
    right.set_ylabel("¥ / 1,000 questions")
    right.set_xticks(xs)
    right.grid(alpha=0.3)
    latency = right.twinx()
    latency.plot(xs, [row["p50_ms"] or 0.0 for row in finished], "-s", ms=3, lw=1.1,
                 color="#7f7f7f", label="p50 latency (ms)")
    latency.set_ylabel("p50 latency (ms)")
    right.set_title("%s: cost and latency" % entry.name, fontsize=10)
    handles = right.get_lines() + latency.get_lines()
    if handles:
        right.legend(handles, [handle.get_label() for handle in handles], fontsize=8)

    if panels == 3:
        stops = axes[2]
        labels = ("first round", "after rewrite", "cap reached")
        fields = ("stop_hit_first_round", "stop_hit_after_rewrite", "stop_cap_reached")
        width = 0.26
        for index, (field, name) in enumerate(zip(fields, labels)):
            stops.bar(
                [x + (index - 1) * width for x in xs],
                [row[field] or 0 for row in finished],
                width=width,
                label=name,
            )
        stops.set_xlabel(entry.x_label)
        stops.set_ylabel("questions")
        stops.set_xticks(xs)
        stops.set_title("stop reason", fontsize=10)
        stops.legend(fontsize=8)

    figure.suptitle("%s sweep (%s)" % (entry.name, entry.x_key), fontsize=11)
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return True


def curve(name: str, runs_root: str = DEFAULT_RUNS_ROOT, out: str = DEFAULT_REPORTS_DIR) -> int:
    """`python scripts/run_sweeps.py --curve <family>`: CSV + PNG + markdown table."""
    try:
        entry = family(name)
    except SweepError as error:
        print("PROBLEM %s" % error, file=sys.stderr)
        return 2
    rows = read_curve(name, runs_root=runs_root)
    os.makedirs(out, exist_ok=True)
    csv_path = os.path.join(out, "%s.csv" % name)
    md_path = os.path.join(out, "%s.md" % name)
    png_path = os.path.join(out, "%s.png" % name)
    _write_csv(csv_path, rows)
    _write_md(md_path, entry, rows, runs_root)
    _plot(png_path, entry, rows)

    finished = [row for row in rows if row["status"] == "finished"]
    print("%s sweep: %d of %d point(s) finished under %s"
          % (name, len(finished), len(rows), runs_root))
    for row in rows:
        if row["status"] != "finished":
            print("  %-11s pending" % row["label"])
            continue
        print(
            "  %-11s %-8s recall@k=%s  cite P=%s  CNY/1k=%s"
            % (
                row["label"],
                row["run_id"].rsplit("-", 1)[-1],
                _cell_text(row["recall_at_k"]),
                _cell_text(row["citation_precision"]),
                _cell_text(row["cny_per_1k"]),
            )
        )
    if entry.name == "hops":
        decided = break_even_hop(rows)
        print(
            "  break-even hop: %s"
            % ("pending (no hops=1 run)" if decided is None else decided)
        )
    print("wrote %s" % os.path.join(out, "%s.{csv,md,png}" % name))
    return 0


def curves(runs_root: str = DEFAULT_RUNS_ROOT, out: str = DEFAULT_REPORTS_DIR) -> int:
    """Write all three curves; a family whose runs are missing is still emitted."""
    worst = 0
    for entry in FAMILIES:
        worst = max(worst, curve(entry.name, runs_root=runs_root, out=out))
    return worst

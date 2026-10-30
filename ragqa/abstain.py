"""Abstention as a calibrated decision.

`generate.abstain_score_threshold` is compared against `retrieved[0]["score"]`,
and that score lives on a different scale in every retrieval mode:

- `dense`: cosine similarity, already in [0, 1].
- `hybrid`: a reciprocal-rank-fusion sum, ~1/(rrf_k + rank), which for k=10 and
  rrf_k=60 lands in roughly [0.015, 0.035] — never near 0.2.
- `rerank`, `llm`: a cross-encoder score in [0, 1], clustered high (0.77–1.00 for
  answerable items in the runs on disk).

Writing one number into the config and pretending it means the same thing in all
three modes is how a system ends up abstaining on everything in hybrid and on
nothing in rerank. So the sweep runs in a per-mode *normalized* space and reports
the raw-scale equivalent of every threshold it prints, which is the number that
can actually be written back into a config.

Normalization is monotone, fitted on the run's own score distribution:

- `identity` for cosine, which is already a bounded similarity.
- `zscore-normal-cdf` for RRF sums and cross-encoder scores: z-score each raw
  score against the mode's own mean and standard deviation, then push it through
  the standard normal CDF, so t is the quantile of a fitted normal. t = 0.5 is
  the mode's mean score, and `inverse(t)` returns the raw threshold. The mapping
  is strictly monotone, so it cannot reorder items, and it is invertible, so the
  raw threshold is exact rather than approximate.

Grid: the ticket fixes both the interval [0.2, 0.9] and the point count (18).
Those are inconsistent at a 0.05 step — [0.2, 0.9] at 0.05 is 15 points — and 18
points across the same interval is the reading that keeps the interval (where a
threshold is meaningful) and the resolution (finer than 0.05 everywhere). The
step is therefore 0.0412, not 0.05.

Two error types are reported separately because they cost different things:
over-abstention on answerable items is a system that withholds what it knows;
under-abstention on near-misses is a system that answers what it does not know.
The working-point rule (stated before the numbers were seen, applied uniformly)
maximises F1 of the answer class subject to over-abstention <= 0.05, and falls
back to the smallest achievable over-abstention rate when the budget is
infeasible. Ties go to the largest t, which buys the widest abstention margin at
the same measured cost.

Everything here is arithmetic over finished run directories. No model is called.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

GRID_MIN = 0.2
GRID_MAX = 0.9
GRID_POINTS = 18
THRESHOLD_GRID: Tuple[float, ...] = tuple(
    round(GRID_MIN + index * (GRID_MAX - GRID_MIN) / (GRID_POINTS - 1), 4)
    for index in range(GRID_POINTS)
)

OVER_ABSTAIN_BUDGET = 0.05
CSV_COLUMNS = (
    "t",
    "precision",
    "recall",
    "over_abstain_rate_on_answerable",
    "under_abstain_rate_on_near_miss",
    "raw_threshold",
)
NEAR_MISS_SNIPPET_CHARS = 200
NEAR_MISS_PER_MODE = 3


class AbstainError(Exception):
    """A sweep input that cannot produce an honest curve."""


# --- score scales ---------------------------------------------------------


@dataclass(frozen=True)
class ScoreTransform:
    """A monotone map from a mode's raw score onto [0, 1]."""

    kind: str
    mean: float = 0.0
    stdev: float = 0.0
    count: int = 0
    low: float = 0.0
    high: float = 0.0

    def forward(self, raw: float) -> float:
        if self.kind == "identity":
            return float(raw)
        value = (float(raw) - self.mean) / self.stdev
        return statistics.NormalDist().cdf(value)

    def inverse(self, normalized: float) -> float:
        if self.kind == "identity":
            return float(normalized)
        clipped = min(max(float(normalized), 1e-6), 1.0 - 1e-6)
        return self.mean + self.stdev * statistics.NormalDist().inv_cdf(clipped)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "fitted_mean": round(self.mean, 6),
            "fitted_stdev": round(self.stdev, 6),
            "fitted_count": self.count,
            "raw_low": round(self.low, 6),
            "raw_high": round(self.high, 6),
            "forward": "identity: p = score"
            if self.kind == "identity"
            else "p = Phi((score - mean) / stdev)",
            "inverse": "raw = p"
            if self.kind == "identity"
            else "raw = mean + stdev * Phi^-1(p)",
        }


IDENTITY = ScoreTransform(kind="identity")


@dataclass(frozen=True)
class ModeSpec:
    """What the mode's raw score means, and how the sweep normalizes it."""

    mode: str
    transform: str
    scale: str
    prefixes: Tuple[str, ...]
    rationale: str


MODES: Dict[str, ModeSpec] = {
    "dense": ModeSpec(
        mode="dense",
        transform="identity",
        scale="cosine similarity in [0, 1] from the dense branch",
        prefixes=("dense", "cosine"),
        rationale="cosine is already a bounded similarity; normalizing it would "
        "discard the meaning of the number the reader recognizes.",
    ),
    "hybrid": ModeSpec(
        mode="hybrid",
        transform="zscore-normal-cdf",
        scale="RRF fused sum, ~1/(rrf_k + rank); with rrf_k=60 and k=10 the observed "
        "range is about [0.015, 0.035], so no threshold in [0.2, 0.9] is reachable raw",
        prefixes=("hybrid",),
        rationale="the RRF sum is an unbounded-ish reciprocal-rank artifact with no "
        "absolute meaning; its z-score against the run's own distribution is the only "
        "comparable quantity, and the inverse maps every t back to a raw sum.",
    ),
    "rerank": ModeSpec(
        mode="rerank",
        transform="zscore-normal-cdf",
        scale="cross-encoder score in [0, 1], clustered high: answerable items in the "
        "runs on disk score 0.77-1.00 while near-misses reach 0.97",
        prefixes=("rerank",),
        rationale="the cross-encoder is calibrated towards the positive class, so its "
        "raw score is not a probability of answerability; the per-mode normal fit keeps "
        "the ordering and makes the sweep's t comparable with the other modes.",
    ),
    "llm": ModeSpec(
        mode="llm",
        transform="zscore-normal-cdf",
        scale="same cross-encoder score as rerank; generation is an LLM, but the "
        "abstain threshold is still compared against the retrieval score",
        prefixes=("llm",),
        rationale="retrieval is rerank, so the scale is rerank's; the mode is swept "
        "separately because generation changes which items ultimately abstain and the "
        "score threshold has to leave room for that.",
    ),
}

MODE_ORDER = tuple(MODES)
IGNORED_PREFIXES = ("smoke", "stub")


def mode_for_run(run_name: str) -> Optional[str]:
    """The retrieval mode a run directory name implies, or None if unroutable.

    Run names are `<family>-<mode>-<timestamp>-<digest>`, where the family says
    whether the run used real components (`real-`) or a stub. Only the mode
    segment decides the score scale, so the family is stripped first.
    """
    tail = run_name[len("real-"):] if run_name.startswith("real-") else run_name
    for mode, spec in MODES.items():
        for prefix in spec.prefixes:
            if tail == prefix or tail.startswith(prefix + "-"):
                return mode
    return None


# --- per-item observations -------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One golden item as one run saw it."""

    item_id: str
    answerable: bool
    top_score: float
    run_id: str = ""
    abstained: bool = False
    retrieved: Tuple[Dict[str, Any], ...] = field(default=())


def _score_of(hit: Dict[str, Any], run_name: str, item_id: str, where: str) -> float:
    if "score" not in hit:
        raise AbstainError(
            f"{run_name}: item {item_id} has a retrieved row at {where} with no "
            "'score' field, so there is no score column to sweep. A curve cannot be "
            "recovered from a run that never recorded the quantity being thresholded."
        )
    try:
        return float(hit["score"])
    except (TypeError, ValueError):
        raise AbstainError(
            f"{run_name}: item {item_id} has a non-numeric score {hit['score']!r} at "
            f"{where}; the sweep needs a number per retrieved chunk."
        )


def load_items(run_dir: Path) -> List[Item]:
    """Every prediction row of one run as an `Item` carrying its top score."""
    run_dir = Path(run_dir)
    predictions = run_dir / "predictions.jsonl"
    if not predictions.exists():
        raise AbstainError(
            f"{run_dir.name}: no predictions.jsonl in the run directory, so there is "
            "nothing to sweep."
        )

    items: List[Item] = []
    with predictions.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            item_id = str(row.get("item_id") or f"line-{line_number}")
            retrieved = row.get("retrieved") or []
            if not retrieved:
                raise AbstainError(
                    f"{run_dir.name}: item {item_id} has no retrieved candidates, so it "
                    "has no top score and cannot sit on an abstention curve."
                )
            scores = [
                _score_of(hit, run_dir.name, item_id, f"rank {hit.get('rank', '?')}")
                for hit in retrieved
            ]
            ordered = sorted(retrieved, key=lambda hit: -float(hit["score"]))
            items.append(
                Item(
                    item_id=item_id,
                    answerable=bool(row.get("answerable", True)),
                    top_score=max(scores),
                    run_id=run_dir.name,
                    abstained=bool(row.get("abstained", False)),
                    retrieved=tuple(
                        {
                            "chunk_id": str(hit.get("chunk_id") or ""),
                            "doc_id": str(hit.get("doc_id") or ""),
                            "rank": int(hit.get("rank") or 0),
                            "score": float(hit["score"]),
                        }
                        for hit in ordered[:3]
                    ),
                )
            )
    if not items:
        raise AbstainError(f"{run_dir.name}: predictions.jsonl is empty.")
    return items


def discover_runs(runs_root: Path) -> Dict[str, List[Path]]:
    """Run directories grouped by mode, oldest first so the newest wins a dedupe."""
    groups, _ = _classify(runs_root)
    return groups


def _classify(runs_root: Path) -> Tuple[Dict[str, List[Path]], List[str]]:
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        raise AbstainError(f"runs root {runs_root} is not a directory.")
    groups: Dict[str, List[Path]] = {}
    skipped: List[str] = []
    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir() or not (entry / "predictions.jsonl").exists():
            continue
        mode = mode_for_run(entry.name)
        if mode is None:
            if not entry.name.startswith(IGNORED_PREFIXES):
                skipped.append(entry.name)
            continue
        groups.setdefault(mode, []).append(entry)
    for paths in groups.values():
        paths.sort(key=lambda path: path.name)
    return groups, skipped


def collect_mode_items(run_paths: Sequence[Path]) -> List[Item]:
    """One row per golden item for a mode; the newest run supersedes older ones.

    Two runs of the same mode over the same golden set would otherwise double
    count every item and inflate the curve's denominator without adding a single
    independent observation.
    """
    merged: Dict[str, Item] = {}
    for path in sorted(Path(p) for p in run_paths):
        for item in load_items(path):
            merged[item.item_id] = item
    if not merged:
        raise AbstainError("no items collected for this mode.")
    return [merged[item_id] for item_id in sorted(merged)]


def fit_transform(scores: Iterable[float], kind: str) -> ScoreTransform:
    """Fit the documented monotone map for a mode on that mode's own scores."""
    values = [float(score) for score in scores]
    if kind not in ("identity", "zscore-normal-cdf"):
        raise AbstainError(
            f"unknown score transform {kind!r}; known: 'identity', 'zscore-normal-cdf'."
        )
    if kind == "identity":
        return ScoreTransform(
            kind="identity",
            mean=statistics.fmean(values) if values else 0.0,
            stdev=statistics.pstdev(values) if len(values) > 1 else 0.0,
            count=len(values),
            low=min(values) if values else 0.0,
            high=max(values) if values else 0.0,
        )
    if len(values) < 2:
        raise AbstainError(
            f"cannot fit {kind}: need at least two scores, got {len(values)}."
        )
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev <= 1e-12:
        raise AbstainError(
            f"cannot fit {kind}: the score column has no spread (all {len(values)} "
            f"values are {mean:.6f}); a z-score of a constant is undefined and any "
            "curve drawn from it would be invented."
        )
    return ScoreTransform(
        kind=kind,
        mean=mean,
        stdev=stdev,
        count=len(values),
        low=min(values),
        high=max(values),
    )


# --- the curve ------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def curve(
    items: Sequence[Item],
    transform: ScoreTransform,
    grid: Sequence[float] = THRESHOLD_GRID,
) -> List[Dict[str, Any]]:
    """One row per threshold: precision/recall plus both abstention error rates."""
    answerable = [item for item in items if item.answerable]
    near_miss = [item for item in items if not item.answerable]
    if not answerable or not near_miss:
        raise AbstainError(
            "an abstention curve needs both classes: got "
            f"{len(answerable)} answerable and {len(near_miss)} near-miss items."
        )

    normalized = [(item, transform.forward(item.top_score)) for item in items]
    positive_scores = sorted(
        (p for item, p in normalized if item.answerable), reverse=True
    )
    negative_scores = sorted((p for item, p in normalized if not item.answerable), reverse=True)

    points: List[Dict[str, Any]] = []
    for t in grid:
        true_positive = sum(1 for p in positive_scores if p >= t)
        false_negative = len(positive_scores) - true_positive
        false_positive = sum(1 for p in negative_scores if p >= t)
        true_negative = len(negative_scores) - false_positive

        precision = _rate(true_positive, true_positive + false_positive)
        recall = _rate(true_positive, len(positive_scores))
        f1 = (
            round(2 * precision * recall / (precision + recall), 6)
            if precision + recall
            else 0.0
        )
        points.append(
            {
                "t": round(float(t), 4),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "over_abstain_rate_on_answerable": _rate(false_negative, len(positive_scores)),
                "under_abstain_rate_on_near_miss": _rate(false_positive, len(negative_scores)),
                "raw_threshold": round(transform.inverse(t), 6),
                "answerable_answered": true_positive,
                "answerable_total": len(positive_scores),
                "near_miss_answered": false_positive,
                "near_miss_total": len(negative_scores),
                "near_miss_abstained": true_negative,
            }
        )
    return points


def choose_working_point(
    points: Sequence[Dict[str, Any]], budget: float = OVER_ABSTAIN_BUDGET
) -> Dict[str, Any]:
    """Best F1 whose over-abstention stays inside budget; ties to the largest t."""
    if not points:
        raise AbstainError("no curve points to choose a working point from.")
    feasible = [p for p in points if p["over_abstain_rate_on_answerable"] <= budget]
    if feasible:
        chosen = max(feasible, key=lambda p: (p["f1"], p["t"]))
        return _annotate(chosen, budget, feasible=True)
    floor = min(p["over_abstain_rate_on_answerable"] for p in points)
    candidates = [p for p in points if p["over_abstain_rate_on_answerable"] == floor]
    chosen = max(candidates, key=lambda p: (p["f1"], p["t"]))
    return _annotate(chosen, budget, feasible=False)


def _annotate(point: Dict[str, Any], budget: float, feasible: bool) -> Dict[str, Any]:
    chosen = dict(point)
    chosen["budget"] = budget
    chosen["constraint_feasible"] = feasible
    return chosen


# --- artifacts ------------------------------------------------------------


def _write_csv(path: Path, points: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for point in points:
            writer.writerow([f"{point[column]:.6g}" if column == "t" else
                             f"{point[column]:.4f}" if isinstance(point[column], float)
                             else point[column] for column in CSV_COLUMNS])


def _plot(path: Path, mode: str, points, chosen, spec: ModeSpec, transform) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:  # pragma: no cover - environment guard
        raise AbstainError(
            f"matplotlib is required to draw {path.name}: {error}. Install it or read "
            "the CSV, which carries the same numbers."
        )

    # Beyond the highest score the mode ever produced, t is an extrapolation of the
    # fitted normal; drawing it would put a precision-0 cliff on the figure that no
    # real threshold can reach. The CSV keeps those rows; the figure does not.
    shown = [point for point in points if point["raw_threshold"] <= transform.high + 1e-9]
    hidden = len(points) - len(shown)

    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2))
    recalls = [p["recall"] for p in shown]
    precisions = [p["precision"] for p in shown]
    left.plot(recalls, precisions, "-o", ms=3.5, lw=1.2, color="#1f4e79")
    left.scatter(
        [chosen["recall"]],
        [chosen["precision"]],
        s=95,
        marker="*",
        zorder=5,
        color="#c00000",
        label=f"working point t={chosen['t']:.4f}\nraw {chosen['raw_threshold']:.6g}",
    )
    left.set_xlabel("recall  (share of answerable items that are answered)")
    left.set_ylabel("precision  (share of answered items that are answerable)")
    left.set_title(
        f"{mode}: abstention precision-recall"
        + (f"\n({hidden} extrapolated point(s) beyond raw {transform.high:.6g} hidden)"
           if hidden else ""),
        fontsize=10,
    )
    left.set_xlim(-0.02, 1.02)
    left.set_ylim(-0.02, 1.05)
    left.grid(alpha=0.3)
    left.legend(loc="lower right", fontsize=8)

    grid = [p["t"] for p in shown]
    right.plot(
        grid,
        [p["over_abstain_rate_on_answerable"] for p in shown],
        "-o",
        ms=3,
        lw=1.2,
        color="#c00000",
        label="over-abstain (answerable)",
    )
    right.plot(
        grid,
        [p["under_abstain_rate_on_near_miss"] for p in shown],
        "-s",
        ms=3,
        lw=1.2,
        color="#2e75b6",
        label="under-abstain (near-miss)",
    )
    right.axhline(OVER_ABSTAIN_BUDGET, ls=":", lw=1, color="#7f7f7f",
                  label=f"budget {OVER_ABSTAIN_BUDGET:.2f}")
    right.axvline(chosen["t"], ls="--", lw=1, color="#404040")
    right.set_xlabel("t  (normalized threshold)")
    right.set_ylabel("rate")
    right.set_title(f"{mode}: the two error types, {spec.transform}", fontsize=10)
    right.set_ylim(-0.02, 1.05)
    right.grid(alpha=0.3)
    right.legend(loc="center right", fontsize=8)

    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _justification(mode: str, chosen, points, spec: ModeSpec, items) -> str:
    answerable = sum(1 for item in items if item.answerable)
    near_miss = len(items) - answerable
    ceiling = max(p["t"] for p in points)
    floor = min(p["t"] for p in points)
    if chosen["constraint_feasible"]:
        opening = (
            f"Applied the pre-registered rule: among the {len(points)} grid points, the "
            f"largest F1 whose over-abstention on answerable items stays inside the "
            f"{chosen['budget']:.2f} budget is F1={chosen['f1']:.4f} at t="
            f"{chosen['t']:.4f}, which is the raw score {chosen['raw_threshold']:.6g} "
            f"for this mode."
        )
    else:
        opening = (
            f"The over-abstention budget of {chosen['budget']:.2f} is infeasible at every "
            f"one of the {len(points)} grid points: even at the lowest t the smallest "
            f"achievable over-abstention is "
            f"{chosen['over_abstain_rate_on_answerable']:.4f}. The rule then asks for the "
            f"smallest over-abstention rate and breaks the tie on F1, which lands on "
            f"t={chosen['t']:.4f} (raw {chosen['raw_threshold']:.6g})."
        )
    body = (
        f" There it answers {chosen['answerable_answered']}/{answerable} answerable items "
        f"(over-abstain {chosen['over_abstain_rate_on_answerable']:.4f}, "
        f"recall {chosen['recall']:.4f}) and answers "
        f"{chosen['near_miss_answered']}/{near_miss} near-misses "
        f"(under-abstain {chosen['under_abstain_rate_on_near_miss']:.4f}), so precision "
        f"is {chosen['precision']:.4f}."
    )
    scale = (
        f" t is on the normalized scale ({spec.transform}): {spec.rationale} The grid "
        f"spans t={floor:.4f}..{ceiling:.4f} on a nominal 0.05 step flattened to 18 "
        f"points over [0.2, 0.9]. Only {chosen['raw_threshold']:.6g} may be written into "
        f"`generate.abstain_score_threshold` for the {mode} mode; the normalized t "
        "transfers nowhere else, and this raw number transfers to no other mode either."
    )
    caveat = (
        f" The curve rests on {answerable} answerable and {near_miss} near-miss items "
        "from golden v0, so every rate moves in steps of "
        f"1/{max(answerable, 1)} and the working point is a v0 estimate until golden v1 "
        "is labelled."
    )
    return opening + body + scale + caveat


def _read_questions(run_dir: Path) -> Dict[str, str]:
    """Question text per item id, from the golden file the run recorded."""
    config_path = Path(run_dir) / "config.json"
    if not config_path.exists():
        return {}
    try:
        items_path = json.loads(config_path.read_text(encoding="utf-8"))["golden"]["items_path"]
    except (KeyError, ValueError, json.JSONDecodeError):
        return {}
    candidates = [Path(items_path), Path.cwd() / items_path]
    for candidate in candidates:
        if candidate.exists():
            questions: Dict[str, str] = {}
            with candidate.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    questions[str(row.get("id"))] = " ".join(str(row.get("question", "")).split())
            return questions
    return {}


def _read_chunk_texts(run_dir: Path, wanted: Iterable[str]) -> Dict[str, str]:
    """Chunk text for the ids in `wanted`, streamed out of the run's chunks.jsonl."""
    path = Path(run_dir) / "chunks.jsonl"
    if not path.exists():
        return {}
    needed = set(wanted)
    texts: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            chunk = json.loads(line)
            chunk_id = str(chunk.get("chunk_id") or "")
            if chunk_id in needed:
                texts[chunk_id] = str(chunk.get("text") or "")
    return texts


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= NEAR_MISS_SNIPPET_CHARS:
        return collapsed
    return collapsed[:NEAR_MISS_SNIPPET_CHARS].rstrip() + " …"


def _hardest_near_misses(items, transform, limit=NEAR_MISS_PER_MODE):
    """The near-misses closest to the threshold: the showcase for the decision."""
    return sorted(
        (item for item in items if not item.answerable),
        key=lambda item: -transform.forward(item.top_score),
    )[:limit]


def _near_miss_section(mode, spec, items, transform, chosen, questions, chunks_by_run) -> str:
    near_miss = _hardest_near_misses(items, transform)
    if not near_miss:
        return ""

    lines = [f"## {mode}", ""]
    lines.append(
        f"Scale: {spec.scale}. Working point: t={chosen['t']:.4f} normalized = raw "
        f"{chosen['raw_threshold']:.6g}. Decision rule: answer iff "
        "normalized(top score) >= t."
    )
    lines.append("")
    for item in near_miss:
        normalized = transform.forward(item.top_score)
        answered = normalized >= chosen["t"]
        verdict = "ANSWERED — under-abstention" if answered else "ABSTAINED — correct"
        lines.append(
            f"### {item.item_id} — {verdict} "
            f"(normalized {normalized:.4f} {'>=' if answered else '<'} t {chosen['t']:.4f})"
        )
        question = questions.get(item.item_id)
        lines.append("")
        lines.append(f"- question: {question}" if question else "- question: (not recorded in the golden file)")
        lines.append(
            f"- run: `{item.run_id}` · top raw score {item.top_score:.6f} · "
            f"run-time abstained: {item.abstained}"
        )
        lines.append("- top retrieved chunks:")
        texts = chunks_by_run.get(item.run_id, {})
        for hit in item.retrieved:
            snippet = _snippet(texts.get(hit["chunk_id"], ""))
            lines.append("")
            lines.append(
                f"  {hit['rank']}. `{hit['chunk_id']}` · {hit['doc_id']} · "
                f"raw {hit['score']:.6f}"
            )
            lines.append(f"     > {snippet or '(chunk text not available in this run directory)'}")
        lines.append("")
    return "\n".join(lines)


def _write_near_miss_examples(path, sections, answerable_counts) -> None:
    header = [
        "# Near-miss items at the chosen working point",
        "",
        "A near-miss is a golden item that is deliberately unanswerable but topically "
        "adjacent: the retrieval score for it looks like the score for a real question. "
        "Each item below is shown with the decision its score produces at that mode's "
        "chosen threshold and with the top three retrieved chunks, so the reader can see "
        "whether the score that was (or was not) sufficient actually pointed at the "
        "passage that nearly answered the question.",
        "",
        "Each item also reports the decision the run itself took (`run-time "
        "abstained`), which can differ from the score-policy decision above it: in the "
        "`llm` runs the model declines items whose score clears the threshold, and in "
        "the `hybrid` runs the score threshold was set below every observed score, so "
        "the run abstained for a different reason or not at all.",
        "",
        "| mode | t | raw threshold | answerable answered | near-miss answered | "
        "over-abstain | under-abstain |",
        "|---|---|---|---|---|---|---|",
    ]
    summary = list(header)
    for mode, chosen, items, _transform, _spec, _questions, _texts in sections:
        answerable = answerable_counts[mode]
        near_miss = len(items) - answerable
        summary.append(
            f"| {mode} | {chosen['t']:.4f} | {chosen['raw_threshold']:.6g} | "
            f"{chosen['answerable_answered']}/{answerable} | "
            f"{chosen['near_miss_answered']}/{near_miss} | "
            f"{chosen['over_abstain_rate_on_answerable']:.4f} | "
            f"{chosen['under_abstain_rate_on_near_miss']:.4f} |"
        )
    body = ["\n".join(summary), ""]
    for mode, chosen, items, transform, spec, questions, chunks_by_run in sections:
        body.append(
            _near_miss_section(mode, spec, items, transform, chosen, questions, chunks_by_run)
        )
    Path(path).write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")


def sweep_command(runs_root, out, modes: Optional[Sequence[str]] = None) -> int:
    """`python -m ragqa sweep abstention --runs runs --out reports [--modes ...]`."""
    runs_root = Path(runs_root)
    out = Path(out)
    try:
        groups, skipped = _classify(runs_root)
    except AbstainError as error:
        print(f"abstention sweep: {error}")
        return 2

    if modes:
        requested = [str(mode) for mode in modes]
        unknown = [mode for mode in requested if mode not in MODES]
        if unknown:
            print(
                f"abstention sweep: unknown mode(s) {unknown}; known modes are "
                f"{list(MODES)}"
            )
            return 2
        absent = [mode for mode in requested if mode not in groups]
        if absent:
            print(
                f"abstention sweep: no finished run for mode(s) {absent} under "
                f"{runs_root}; found {sorted(groups)}"
            )
            return 2
        order = [mode for mode in MODE_ORDER if mode in requested]
    else:
        order = [mode for mode in MODE_ORDER if mode in groups]

    if not order:
        print(f"abstention sweep: no run directories recognised under {runs_root}")
        return 2

    directory = out / "abstention"
    directory.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "protocol": {
            "grid": {
                "min": GRID_MIN,
                "max": GRID_MAX,
                "points": GRID_POINTS,
                "nominal_step": 0.05,
                "actual_step": round((GRID_MAX - GRID_MIN) / (GRID_POINTS - 1), 6),
                "note": "the ticket fixes the interval [0.2, 0.9] and 18 points; at a "
                "0.05 step that interval holds 15 points, so the step is flattened to "
                "0.0412 rather than moving either endpoint",
            },
            "positive": "an answerable golden item: it should be answered",
            "negative": "a near-miss golden item: it should be abstained on",
            "decision": "answer iff transform(top_score) >= t, matching "
            "generate.py, which abstains when score < threshold",
            "working_point_rule": "maximise F1 of the answer class subject to "
            "over_abstain_rate_on_answerable <= 0.05; if infeasible at every t, choose "
            "the smallest over-abstain rate and break ties on F1; ties always go to the "
            "largest t",
            "budget": OVER_ABSTAIN_BUDGET,
            "dedupe": "one row per golden item_id per mode; when a mode has several runs "
            "the newest supersedes the older",
            "score": "top score = max over retrieved[] score, the quantity "
            "generate.abstain_score_threshold is compared against",
        },
        "runs_root": str(runs_root),
        "unrouted_runs": skipped,
        "sources": {},
        "modes": {},
    }

    sections = []
    answerable_counts: Dict[str, int] = {}
    summary_rows: List[Dict[str, Any]] = []
    for mode in order:
        spec = MODES[mode]
        run_paths = groups[mode]
        try:
            items = collect_mode_items(run_paths)
            transform = fit_transform((item.top_score for item in items), spec.transform)
            points = curve(items, transform)
            chosen = choose_working_point(points)
        except AbstainError as error:
            print(f"abstention sweep ({mode}): {error}")
            return 2

        _write_csv(directory / f"{mode}-pr.csv", points)
        _plot(directory / f"{mode}-pr.png", mode, points, chosen, spec, transform)

        answerable = sum(1 for item in items if item.answerable)
        near_miss = len(items) - answerable
        retained: Dict[str, int] = {}
        for item in items:
            retained[item.run_id] = retained.get(item.run_id, 0) + 1
        answerable_counts[mode] = answerable
        payload["modes"][mode] = {
            **{key: chosen[key] for key in (
                "t",
                "raw_threshold",
                "precision",
                "recall",
                "f1",
                "over_abstain_rate_on_answerable",
                "under_abstain_rate_on_near_miss",
                "answerable_answered",
                "answerable_total",
                "near_miss_answered",
                "near_miss_total",
                "constraint_feasible",
                "budget",
            )},
            "config_write_back": {
                "key": "generate.abstain_score_threshold",
                "value": chosen["raw_threshold"],
                "mode": mode,
            },
            "curve": {
                "precision_at_t_min": points[0]["precision"],
                "precision_at_t_max": points[-1]["precision"],
                "best_f1": max(point["f1"] for point in points),
                "best_f1_t": max(points, key=lambda point: point["f1"])["t"],
                "f1_at_t_min": points[0]["f1"],
                "f1_at_t_max": points[-1]["f1"],
                "points": len(points),
            },
            "transform": transform.as_dict(),
            "grid_support": {
                "observed_raw_low": round(transform.low, 6),
                "observed_raw_high": round(transform.high, 6),
                "t_raw_above_observed_high": [
                    point["t"] for point in points
                    if point["raw_threshold"] > transform.high + 1e-9
                ],
                "note": "those t points sit past the highest score any run in this mode "
                "produced, so their raw thresholds are extrapolations of the fitted "
                "normal rather than reachable numbers; they stay in the curve for "
                "completeness and are never candidates for the working point, which "
                "must be a threshold the system can actually cross",
            },
            "scale": spec.scale,
            "runs": [path.name for path in run_paths],
            "items": {"answerable": answerable, "near_miss": near_miss, "total": len(items)},
            "justification": _justification(mode, chosen, points, spec, items),
            "artifacts": [
                f"{mode}-pr.csv",
                f"{mode}-pr.png",
                "near-miss-examples.md",
            ],
        }
        payload["sources"][mode] = {
            path.name: {
                "items_in_run": len(load_items(path)),
                "rows_retained": retained.get(path.name, 0),
            }
            for path in run_paths
        }

        # The showcase needs text, which lives in the run's own chunks.jsonl; read
        # only the chunk ids the displayed near-misses actually cite.
        by_run_id = {path.name: path for path in run_paths}
        wanted: Dict[str, set] = {}
        for item in _hardest_near_misses(items, transform):
            path = by_run_id.get(item.run_id)
            if path is None:
                continue
            wanted.setdefault(item.run_id, set()).update(
                hit["chunk_id"] for hit in item.retrieved
            )
        chunks_by_run = {
            run_id: _read_chunk_texts(by_run_id[run_id], ids)
            for run_id, ids in wanted.items()
        }
        sections.append(
            (
                mode,
                chosen,
                items,
                transform,
                spec,
                _read_questions(run_paths[-1]),
                chunks_by_run,
            )
        )
        summary_rows.append(
            {
                "mode": mode,
                "chosen": chosen,
                "answerable": answerable,
                "near_miss": near_miss,
                "runs": len(run_paths),
            }
        )

    (directory / "working-points.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    _write_near_miss_examples(
        directory / "near-miss-examples.md", sections, answerable_counts
    )

    for row in summary_rows:
        chosen = row["chosen"]
        print(
            f"{row['mode']:<7} t={chosen['t']:.4f} raw={chosen['raw_threshold']:.6g} "
            f"P={chosen['precision']:.3f} R={chosen['recall']:.3f} F1={chosen['f1']:.3f} "
            f"over={chosen['over_abstain_rate_on_answerable']:.3f} "
            f"under={chosen['under_abstain_rate_on_near_miss']:.3f} "
            f"({'feasible' if chosen['constraint_feasible'] else 'budget infeasible'}) "
            f"n={row['answerable']}+{row['near_miss']} from {row['runs']} run(s)"
        )
    print(f"wrote {directory}")
    return 0

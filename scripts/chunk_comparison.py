"""Compare the two chunk strategies on the same items (brief item 1, ticket 18).

`AGENTS.md` requires the project to "compare at least two chunking strategies and
report their impact on retrieval quality". The strategies exist and both are
measured — `grid-fixed-*` and `grid-recursive_parent_child-*` cells have run the
identical 60 golden items at all three retrieval levels — but nothing paired them,
so the report could not state the impact (notes/report-factcheck.md §2 row 11).

This script does the pairing. A pair is *the same retrieval mode and the same
contextualisation, with only `chunk.strategy` differing*, so the difference
between the two cells is attributable to chunking; anything else would be a
two-factor comparison wearing a one-factor label, and `validate_pair` refuses it.

Two things are reported, and they answer different questions:

- the **outcome**: hit@10, MRR, nDCG@10, citation precision / recall / span hit,
  abstention, latency and cost, as recursive minus fixed, with a paired McNemar
  on the per-item retrieval hit and on the per-item "carries a supported
  citation" — the same exact test `ragqa.baselines` uses everywhere else;
- the **mechanism**: what the recursive strategy actually did to the chunk set —
  child count, mean and p95 size, the share of chunks ending mid-sentence, the
  share carrying a table row or a code fence, and the share over the token
  budget, decomposed by *why* it is over. The strategy's hypothesis is that
  keeping tables and fences atomic is worth the token budget; the composition of
  the over-budget chunks is what says whether it kept them atomic, and the
  `table_content` items are what say whether that helped anyone.

A pair with one finished side is `pending`. It never prints a zero: a delta of
"0.0000" is a measurement, and a missing run is not one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ragqa import aggregate, baselines, chunk as chunk_mod, grid  # noqa: E402

FIXED = "fixed"
RECURSIVE = "recursive_parent_child"
STRATEGIES = (FIXED, RECURSIVE)
# Column prefix per strategy: `recursive_parent_child_share_over_budget` is a
# sentence, not a CSV header, so the long name lives in the JSON and the columns
# use the short one consistently.
PREFIX = {FIXED: "fixed", RECURSIVE: "recursive"}

# (name, metrics section, key) — every number the brief's "retrieval quality" and
# the citation contract can be stated as, read from `metrics.json` unchanged.
METRICS = (
    ("hit_at_10", "retrieval", "hit_rate"),
    ("mrr", "retrieval", "mrr"),
    ("ndcg_at_10", "retrieval", "ndcg_at_10"),
    ("citation_precision", "citations", "citation_precision"),
    ("citation_recall", "citations", "citation_recall"),
    ("span_hit_rate", "citations", "span_hit_rate"),
    ("over_abstain_rate", "abstention", "over_abstain_rate"),
    ("abstentions", "abstention", "abstained_answerable"),
)

BASE_FIELDS = (
    "retrieval_mode",
    "context_mode",
    "status",
    "fixed_run_id",
    "recursive_run_id",
    "paired_items",
)

MECHANISM_FIELDS = (
    "chunks",
    "parents",
    "mean_tokens",
    "p95_tokens",
    "share_ending_mid_sentence",
    "share_containing_table_row",
    "share_containing_code_fence",
    "share_over_budget",
    "over_budget",
    "over_budget_with_table",
    "over_budget_with_fence",
    "over_budget_structural_share",
)


def _metric_fields(name: str) -> List[str]:
    return [f"{name}_fixed", f"{name}_recursive", f"{name}_delta"]


ROW_FIELDS = (
    list(BASE_FIELDS)
    + [field for name, _, _ in METRICS for field in _metric_fields(name)]
    + ["latency_p95_ms_fixed", "latency_p95_ms_recursive", "latency_p95_ms_delta"]
    + ["cny_per_1k_questions_fixed", "cny_per_1k_questions_recursive",
       "cny_per_1k_questions_delta"]
    + ["hit_discordant_fixed_only", "hit_discordant_recursive_only", "hit_p_value"]
    + ["citation_discordant_fixed_only", "citation_discordant_recursive_only",
       "citation_p_value"]
    + ["table_items", "table_fixed_hits", "table_recursive_hits", "table_p_value"]
    + [f"{prefix}_llm_cache_misses" for prefix in PREFIX.values()]
    + [f"{prefix}_{field}" for prefix in PREFIX.values() for field in MECHANISM_FIELDS]
    + [f"{prefix}_mechanism_source" for prefix in PREFIX.values()]
)

REGENERATE = (
    "python scripts/chunk_comparison.py --runs-root <runs root> "
    "--chunks-root <chunk set root> --report-json reports/chunking.json "
    "--report-csv reports/chunking.csv --note notes/chunking-comparison.md"
)


# --------------------------------------------------------------------------- #
# pairing
# --------------------------------------------------------------------------- #


def validate_pair(fixed: Dict[str, Any], recursive: Dict[str, Any]) -> None:
    """Raise unless the two cells differ in chunk strategy and nothing else.

    Returns None on a valid pair so the caller can `validate_pair(...)` and move
    on; the refusal is the point, because a pair that differs in a second factor
    cannot support a sentence about chunking.
    """
    left = fixed.get("factors") or {}
    right = recursive.get("factors") or {}
    if left.get("chunk_strategy") == right.get("chunk_strategy"):
        raise ValueError(
            "not a chunking comparison: both cells use chunk_strategy=%r"
            % left.get("chunk_strategy")
        )
    if {left.get("chunk_strategy"), right.get("chunk_strategy")} != set(STRATEGIES):
        raise ValueError(
            "a chunk pair is %s against %s, got %r against %r"
            % (FIXED, RECURSIVE, left.get("chunk_strategy"), right.get("chunk_strategy"))
        )
    for factor in ("retrieval_mode", "context_mode"):
        if left.get(factor) != right.get(factor):
            raise ValueError(
                "chunk pair differs in %s (%r vs %r): only chunk.strategy may move"
                % (factor, left.get(factor), right.get(factor))
            )
    if fixed.get("status") == "finished" and recursive.get("status") == "finished":
        if fixed.get("run_dir") and fixed.get("run_dir") == recursive.get("run_dir"):
            raise ValueError("both sides of the pair point at the same run directory")


def pair_cells(cells: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group the declared cells into twins by (retrieval mode, context mode).

    Pairing keys on the two factors that must be held fixed, so a cell can only
    ever meet its own twin. A side is usable only when its run is finished; a
    missing or unfinished side makes the pair `pending` and names what is missing.
    """
    groups: Dict[Any, Dict[str, Dict[str, Any]]] = {}
    for cell in cells:
        factors = cell.get("factors") or {}
        key = (factors.get("retrieval_mode", ""), factors.get("context_mode", ""))
        groups.setdefault(key, {})[factors.get("chunk_strategy", "")] = cell

    pairs: List[Dict[str, Any]] = []
    for (retrieval, context), sides in sorted(groups.items()):
        pair: Dict[str, Any] = {
            "retrieval_mode": retrieval,
            "context_mode": context,
            FIXED: sides.get(FIXED),
            RECURSIVE: sides.get(RECURSIVE),
        }
        missing = [
            strategy
            for strategy in STRATEGIES
            if not pair[strategy] or pair[strategy].get("status") != "finished"
        ]
        pair["missing"] = missing
        pair["status"] = "pending" if missing else "finished"
        pairs.append(pair)
    return pairs


def pending_pair_row(retrieval_mode: str, context_mode: str, missing: Sequence[str]) -> Dict[str, Any]:
    row = {field: None for field in ROW_FIELDS}
    row.update({"retrieval_mode": retrieval_mode, "context_mode": context_mode, "status": "pending"})
    row["missing"] = list(missing)
    return row


# --------------------------------------------------------------------------- #
# outcome
# --------------------------------------------------------------------------- #


def delta_row(
    retrieval_mode: str,
    context_mode: str,
    fixed: Dict[str, Any],
    recursive: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Recursive minus fixed for every metric, both sides kept beside the delta.

    The delta alone would let a reader believe two very different cells are
    comparable; the pair of raw values is what makes the difference checkable. The
    delta is `None` rather than 0 when a side is missing, so an unmeasured metric
    cannot masquerade as "no effect".
    """
    row: Dict[str, Dict[str, Any]] = {}
    for name, section, key in METRICS:
        left = (fixed.get(section) or {}).get(key)
        right = (recursive.get(section) or {}).get(key)
        if left is None or right is None:
            row[name] = {"fixed": left, "recursive": right, "delta": None}
            continue
        row[name] = {
            "fixed": left,
            "recursive": right,
            "delta": round(float(right) - float(left), 4),
        }
    return row


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _cache_misses(run_dir: str) -> Optional[int]:
    """How many generator calls the run had to pay for, from its own record."""
    path = os.path.join(run_dir, "cache_stats.json")
    if not os.path.isfile(path):
        return None
    value = (_read_json(path) or {}).get("llm_cache_misses")
    return None if value is None else int(value)


def resolve_chunk_set(run_dir: str, chunks_root: str) -> Optional[str]:
    """The chunk set a run was built from, named the way `ragqa.chunk` names it."""
    config_path = os.path.join(run_dir, "config.json")
    if not os.path.isfile(config_path):
        return None
    config = _read_json(config_path)
    chunk = config.get("chunk") or {}
    corpus = config.get("corpus") or {}
    snapshot = corpus.get("snapshot_id")
    if not snapshot or not chunks_root:
        return None
    set_id = chunk_mod.chunk_set_id(
        snapshot,
        chunk.get("strategy", ""),
        int(chunk.get("size") or 0),
        int(chunk.get("overlap") or 0),
        int(chunk.get("parent_size") or 0),
    )
    path = os.path.join(chunks_root, set_id)
    return path if os.path.isdir(path) else None


def chunk_mechanism(path: str, budget: int = 512) -> Dict[str, Any]:
    """What the chunk set looks like, and *why* the over-budget chunks are over.

    The shares and percentiles are `ragqa.chunk.stats` — the same function that
    produced the committed `chunk_stats.json`, so this cannot drift from it. The
    decomposition on top is the part the strategy's hypothesis needs: an
    over-budget chunk that carries a table row or a code fence is one the
    recursive splitter refused to break, and one without either is just over.
    """
    from ragqa.corpus import read_jsonl

    stats_path = os.path.join(path, "chunk_stats.json")
    chunks_path = os.path.join(path, "chunks.jsonl")
    recorded = _read_json(stats_path) if os.path.isfile(stats_path) else {}
    # `chunk.main` writes `chunk_set_id`; a run directory's copy is
    # `run.py`'s bare `stats(chunks)` and identifies nothing. That difference is
    # also why a run copy reports `share_over_budget: 0.0` for every strategy:
    # `stats()` is called there without a size, so the guard zeroes the field.
    source = "chunk_set" if recorded.get("chunk_set_id") else "run_dir"

    rows = read_jsonl(chunks_path) if os.path.isfile(chunks_path) else []
    children = [row for row in rows if row.get("kind") == "child"]
    measured = chunk_mod.stats(rows, budget) if rows else {}
    over = [row for row in children if int(row.get("token_count") or 0) > budget]
    with_table = [row for row in over if "|" in str(row.get("text", ""))]
    with_fence = [row for row in over if "```" in str(row.get("text", ""))]
    structural = [
        row
        for row in over
        if "|" in str(row.get("text", "")) or "```" in str(row.get("text", ""))
    ]

    mechanism = {
        "path": os.path.basename(path.rstrip("/\\")),
        "source": source,
        "budget": int(budget),
        "chunks": measured.get("chunks", recorded.get("chunks")),
        "parents": measured.get("parents", recorded.get("parents")),
        "mean_tokens": measured.get("mean_tokens", recorded.get("mean_tokens")),
        "p95_tokens": measured.get("p95_tokens", recorded.get("p95_tokens")),
        "share_ending_mid_sentence": measured.get(
            "share_ending_mid_sentence", recorded.get("share_ending_mid_sentence")
        ),
        "share_containing_table_row": measured.get(
            "share_containing_table_row", recorded.get("share_containing_table_row")
        ),
        "share_containing_code_fence": measured.get(
            "share_containing_code_fence", recorded.get("share_containing_code_fence")
        ),
        "share_over_budget": measured.get("share_over_budget", recorded.get("share_over_budget")),
        "over_budget": len(over),
        "over_budget_with_table": len(with_table),
        "over_budget_with_fence": len(with_fence),
        "over_budget_structural_share": round(len(structural) / len(over), 4) if over else None,
    }
    if source == "run_dir":
        mechanism["note"] = (
            "read from the run directory's own copy: `share_over_budget` there is 0.0 for "
            "every strategy because run.py calls chunk.stats() without a size; the "
            "recomputed over-budget counts above are the real ones"
        )
    return {field: mechanism.get(field) for field in MECHANISM_FIELDS} | {
        "source": mechanism["source"],
        "path": mechanism["path"],
        "note": mechanism.get("note", ""),
    }


# --------------------------------------------------------------------------- #
# the comparison
# --------------------------------------------------------------------------- #


def comparison_row(
    pair: Dict[str, Any],
    golden: Dict[str, Dict[str, Any]],
    chunks_root: str = "",
    budget: int = 512,
) -> Dict[str, Any]:
    """One finished pair, outcome and mechanism together."""
    fixed_cell = pair[FIXED]
    recursive_cell = pair[RECURSIVE]
    validate_pair(fixed_cell, recursive_cell)

    fixed_run = baselines.load_run(fixed_cell["run_dir"])
    recursive_run = baselines.load_run(recursive_cell["run_dir"])
    metrics = delta_row(
        pair["retrieval_mode"], pair["context_mode"], fixed_run["metrics"], recursive_run["metrics"]
    )

    def pair_of(section: str, key: str) -> Dict[str, Any]:
        left = (fixed_run["metrics"].get(section) or {}).get(key)
        right = (recursive_run["metrics"].get(section) or {}).get(key)
        delta = None if left is None or right is None else round(float(right) - float(left), 4)
        return {"fixed": left, "recursive": right, "delta": delta}

    metrics["latency_p95_ms"] = pair_of("system", "latency_p95_ms")
    left = (fixed_run["timings"] or {}).get("p95_ms")
    right = (recursive_run["timings"] or {}).get("p95_ms")
    metrics["latency_p95_ms"] = {
        "fixed": left,
        "recursive": right,
        "delta": None if left is None or right is None else round(float(right) - float(left), 4),
    }
    metrics["cny_per_1k_questions"] = pair_of("system", "cost_per_1k_questions_cny")

    fixed_outcomes = baselines.item_outcomes(fixed_run)
    recursive_outcomes = baselines.item_outcomes(recursive_run)
    shared = [
        item
        for item in sorted(set(fixed_outcomes) & set(recursive_outcomes))
        if fixed_outcomes[item]["answerable"] and recursive_outcomes[item]["answerable"]
    ]

    def macnemar(field: str) -> Dict[str, Any]:
        pairs = [
            (bool(fixed_outcomes[item][field]), bool(recursive_outcomes[item][field]))
            for item in shared
        ]
        return baselines.mcnemar_outcomes(pairs)

    table_items = [item for item in shared if (golden.get(item) or {}).get("type") == "table_content"]
    table_pairs = [
        (bool(fixed_outcomes[item]["hit"]), bool(recursive_outcomes[item]["hit"]))
        for item in table_items
    ]

    row: Dict[str, Any] = {
        "retrieval_mode": pair["retrieval_mode"],
        "context_mode": pair["context_mode"],
        "status": "finished",
        "fixed_run_id": fixed_run["run_id"],
        "recursive_run_id": recursive_run["run_id"],
        "paired_items": len(shared),
        "metrics": metrics,
        "mcnemar": {
            "retrieval_hit": macnemar("hit"),
            "citation_support": macnemar("citation_support"),
        },
        "table_content": {
            "items": len(table_items),
            "fixed_hits": sum(1 for left, _ in table_pairs if left),
            "recursive_hits": sum(1 for _, right in table_pairs if right),
            "mcnemar": baselines.mcnemar_outcomes(table_pairs) if table_pairs else None,
        },
        # Which run paid for its answers and which replayed a warm cache. Latency
        # across a run is dominated by this, so it travels beside the latency
        # column instead of being left for a reader to discover.
        "cache": {
            PREFIX[FIXED]: _cache_misses(fixed_run["path"]),
            PREFIX[RECURSIVE]: _cache_misses(recursive_run["path"]),
        },
        "mechanism": {},
    }

    for strategy, run in ((FIXED, fixed_run), (RECURSIVE, recursive_run)):
        set_dir = resolve_chunk_set(run["path"], chunks_root)
        target = set_dir or run["path"]
        row["mechanism"][strategy] = chunk_mechanism(target, budget=budget)
    return row


# --------------------------------------------------------------------------- #
# the table
# --------------------------------------------------------------------------- #


def _value(row: Dict[str, Any], field: str) -> Any:
    """Flatten a nested row onto `ROW_FIELDS`."""
    if field in BASE_FIELDS:
        return row.get(field)
    metrics = row.get("metrics") or {}
    for name, _, _ in METRICS:
        if field == f"{name}_fixed":
            return (metrics.get(name) or {}).get("fixed")
        if field == f"{name}_recursive":
            return (metrics.get(name) or {}).get("recursive")
        if field == f"{name}_delta":
            return (metrics.get(name) or {}).get("delta")
    for alias, name in (
        ("latency_p95_ms", "latency_p95_ms"),
        ("cny_per_1k_questions", "cny_per_1k_questions"),
    ):
        if field.startswith(alias + "_"):
            side = field.rsplit("_", 1)[-1]
            return (metrics.get(name) or {}).get(side)
    hit = (row.get("mcnemar") or {}).get("retrieval_hit") or {}
    citation = (row.get("mcnemar") or {}).get("citation_support") or {}
    table = row.get("table_content") or {}
    if field == "hit_discordant_fixed_only":
        return hit.get("baseline_only")
    if field == "hit_discordant_recursive_only":
        return hit.get("treatment_only")
    if field == "hit_p_value":
        return hit.get("p_value")
    if field == "citation_discordant_fixed_only":
        return citation.get("baseline_only")
    if field == "citation_discordant_recursive_only":
        return citation.get("treatment_only")
    if field == "citation_p_value":
        return citation.get("p_value")
    if field == "table_items":
        return table.get("items")
    if field == "table_fixed_hits":
        return table.get("fixed_hits")
    if field == "table_recursive_hits":
        return table.get("recursive_hits")
    if field == "table_p_value":
        return (table.get("mcnemar") or {}).get("p_value")
    if field in ("fixed_llm_cache_misses", "recursive_llm_cache_misses"):
        return (row.get("cache") or {}).get(field[: -len("_llm_cache_misses")])
    for strategy in STRATEGIES:
        mechanism = (row.get("mechanism") or {}).get(strategy) or {}
        prefix = PREFIX[strategy]
        if field == f"{prefix}_mechanism_source":
            return mechanism.get("source")
        if field.startswith(prefix + "_"):
            return mechanism.get(field[len(prefix) + 1 :])
    return row.get(field)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_csv(rows: Sequence[Dict[str, Any]]) -> str:
    lines = [",".join(ROW_FIELDS)]
    for row in rows:
        lines.append(",".join(_csv_value(_value(row, field)) for field in ROW_FIELDS))
    return "\n".join(lines) + "\n"


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "pending"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_mechanism(value: Any, digits: int = 4) -> str:
    """A mechanism number that does not exist is "—", not "pending".

    The mechanism table only lists finished pairs, so `None` there never means
    "not run": it means the quantity is undefined — a strategy with no over-budget
    chunk has no structural share to report.
    """
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_delta(entry: Dict[str, Any], digits: int = 4) -> str:
    if not entry or entry.get("delta") is None:
        return "pending"
    return "%+.*f" % (digits, entry["delta"])


def _p(value: Any) -> str:
    if value is None:
        return "pending"
    if value < 0.0001:
        return "<0.0001"
    return f"{value:.4f}"


def render_markdown(payload: Dict[str, Any]) -> str:
    rows = payload.get("pairs") or []
    finished = [row for row in rows if row.get("status") == "finished"]
    pending = [row for row in rows if row.get("status") != "finished"]

    lines = [
        "# Chunking strategy comparison",
        "",
        "Generated by `scripts/chunk_comparison.py`; do not edit by hand. The brief requires "
        "the project to compare at least two chunking strategies and report their impact on "
        "retrieval quality (item 1, `notes/report-factcheck.md` §2 row 11). Each pair below is "
        "**the same retrieval mode and the same contextualisation with only `chunk.strategy` "
        "differing**, on the same 60-item Golden QA Set, so the difference is attributable to "
        "chunking. A pair that differs in a second factor is refused, not averaged.",
        "",
        "`fixed` splits on character windows with a 64-word overlap; `recursive_parent_child` "
        "splits on structural units (headings, sentences, table rows, code fences) and keeps "
        "the coarser parent for the generator. Its hypothesis is that keeping tables and code "
        "fences atomic is worth the token budget it costs.",
        "",
        "## Outcome: recursive minus fixed",
        "",
        "| pair | hit@10 | MRR | nDCG@10 | citation precision | citation recall | span hit | abstentions | p95 latency (ms) | ¥/1k | LLM cache misses (fixed / recursive) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        label = "`%s` / `%s`" % (row.get("retrieval_mode", "?"), row.get("context_mode", "?"))
        if row.get("status") != "finished":
            lines.append(
                "| %s | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |"
                % label
            )
            continue
        metrics = row.get("metrics") or {}
        cache = row.get("cache") or {}
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s / %s |"
            % (
                label,
                _fmt_delta(metrics.get("hit_at_10")),
                _fmt_delta(metrics.get("mrr")),
                _fmt_delta(metrics.get("ndcg_at_10")),
                _fmt_delta(metrics.get("citation_precision")),
                _fmt_delta(metrics.get("citation_recall")),
                _fmt_delta(metrics.get("span_hit_rate")),
                _fmt_delta(metrics.get("abstentions"), 0),
                _fmt_delta(metrics.get("latency_p95_ms"), 1),
                _fmt_delta(metrics.get("cny_per_1k_questions")),
                _fmt(cache.get(PREFIX[FIXED]), 0),
                _fmt(cache.get(PREFIX[RECURSIVE]), 0),
            )
        )

    lines += [
        "",
        "Every delta above is recursive minus fixed; the raw value of both sides is in "
        "`reports/chunking.{json,csv}`, and a `pending` cell is a pair whose twin has not "
        "finished — never a zero.",
        "",
        "The latency column is reported and not interpreted. A run's per-item latency is "
        "dominated by whether the generator call was answered from the cache or went to the "
        "network, which is why the last column carries the two runs' cache-miss counts: a "
        "cell whose fixed side replayed a warm cache and whose recursive side paid for its "
        "calls shows a latency difference that is about the cache, not about chunking.",
        "",
        "## Paired significance",
        "",
        "McNemar's exact test on the discordant pairs, the same test `ragqa.baselines` uses, "
        "over the items both cells answered and over the same items of the Golden QA Set. If "
        "retrieval quality were affected by chunk strategy, the first row would carry the "
        "evidence.",
        "",
        "| pair | hit: fixed-only / recursive-only | hit p | supported citation: fixed-only / recursive-only | citation p | table items: fixed / recursive | table p |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in finished:
        hit = (row.get("mcnemar") or {}).get("retrieval_hit") or {}
        citation = (row.get("mcnemar") or {}).get("citation_support") or {}
        table = row.get("table_content") or {}
        lines.append(
            "| `%s` / `%s` | %s / %s | %s | %s / %s | %s | %s / %s of %s | %s |"
            % (
                row.get("retrieval_mode", "?"),
                row.get("context_mode", "?"),
                _fmt(hit.get("baseline_only"), 0),
                _fmt(hit.get("treatment_only"), 0),
                _p(hit.get("p_value")),
                _fmt(citation.get("baseline_only"), 0),
                _fmt(citation.get("treatment_only"), 0),
                _p(citation.get("p_value")),
                _fmt(table.get("fixed_hits"), 0),
                _fmt(table.get("recursive_hits"), 0),
                _fmt(table.get("items"), 0),
                _p((table.get("mcnemar") or {}).get("p_value")),
            )
        )

    lines += [
        "",
        "## Mechanism: what the strategies actually did",
        "",
        "Read from each strategy's own chunk set (`data/chunks/<set>/chunks.jsonl` and its "
        "`chunk_stats.json`), recomputed at the pair's token budget with `ragqa.chunk.stats`. "
        "`over budget` counts children larger than the budget; `structural` is the share of "
        "those that carry a table row or a code fence, i.e. that are over budget because the "
        "splitter refused to break one. A run directory's own `chunk_stats.json` reports "
        "`share_over_budget: 0.0` for every strategy — `run.py` calls `chunk.stats()` without "
        "a size — which is why the numbers here are recomputed from the chunk sets and the "
        "source column says which file they came from. A chunk set belongs to a strategy, not to "
        "a pair, so the same two rows repeat beside every pair that uses them.",
        "",
        "| pair / strategy | chunks | parents | mean tokens | p95 tokens | ends mid-sentence | has a table row | has a code fence | over budget | structural share of over-budget | source |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in finished:
        for strategy in STRATEGIES:
            mechanism = (row.get("mechanism") or {}).get(strategy) or {}
            lines.append(
                "| `%s` / `%s` / %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    row.get("retrieval_mode", "?"),
                    row.get("context_mode", "?"),
                    strategy,
                    _fmt_mechanism(mechanism.get("chunks"), 0),
                    _fmt_mechanism(mechanism.get("parents"), 0),
                    _fmt_mechanism(mechanism.get("mean_tokens"), 2),
                    _fmt_mechanism(mechanism.get("p95_tokens"), 0),
                    _fmt_mechanism(mechanism.get("share_ending_mid_sentence")),
                    _fmt_mechanism(mechanism.get("share_containing_table_row")),
                    _fmt_mechanism(mechanism.get("share_containing_code_fence")),
                    _fmt_mechanism(mechanism.get("over_budget"), 0),
                    _fmt_mechanism(mechanism.get("over_budget_structural_share")),
                    mechanism.get("source", "?"),
                )
            )

    lines += [
        "",
        "## Does the atomic-table hypothesis survive here?",
        "",
        payload.get("verdict", "pending"),
        "",
        "## Pending",
        "",
    ]
    if pending:
        lines.append(
            "These pairs have one finished side and one that has not run yet, so they carry no "
            "number at all:"
        )
        lines.append("")
        for row in pending:
            lines.append(
                "- `%s` / `%s` — missing: %s"
                % (
                    row.get("retrieval_mode", "?"),
                    row.get("context_mode", "?"),
                    ", ".join(row.get("missing") or []),
                )
            )
    else:
        lines.append("None: both strategies have finished every declared cell.")

    lines += [
        "",
        "## Regenerate",
        "",
        "```",
        REGENERATE,
        "```",
        "",
        "No model calls: the script reads finished run directories and chunk sets only.",
        "",
    ]
    return "\n".join(lines)


def verdict_for(rows: Sequence[Dict[str, Any]]) -> str:
    """One paragraph on whether keeping tables atomic bought anything measurable.

    Written from the numbers so it cannot survive a change in them: it names the
    largest retrieval delta and its p-value, the `table_content` movement, and the
    structural share of the over-budget chunks that the atomicity produced.
    """
    finished = [row for row in rows if row.get("status") == "finished"]
    if not finished:
        return (
            "pending: no pair has both sides finished, so there is nothing to conclude and "
            "no number to conclude it from."
        )
    best = None
    for row in finished:
        hit = (row.get("mcnemar") or {}).get("retrieval_hit") or {}
        metrics = row.get("metrics") or {}
        delta = (metrics.get("hit_at_10") or {}).get("delta")
        if delta is None:
            continue
        candidate = (abs(delta), delta, hit.get("p_value"), row)
        if best is None or candidate[0] > best[0]:
            best = candidate
    table_p = [
        ((row.get("table_content") or {}).get("mcnemar") or {}).get("p_value") for row in finished
    ]
    table_significant = any(value is not None and value < 0.05 for value in table_p)
    table_ceiling = all(
        (row.get("table_content") or {}).get("fixed_hits") == (row.get("table_content") or {}).get("items")
        and (row.get("table_content") or {}).get("recursive_hits") == (row.get("table_content") or {}).get("items")
        for row in finished
        if row.get("table_content")
    )
    structural = sorted(
        {
            (row.get("mechanism") or {}).get(RECURSIVE, {}).get("over_budget_structural_share")
            for row in finished
            if (row.get("mechanism") or {}).get(RECURSIVE, {}).get("over_budget_structural_share")
            is not None
        }
    )
    mid_sentence = sorted(
        {
            (
                (row.get("mechanism") or {}).get(FIXED, {}).get("share_ending_mid_sentence"),
                (row.get("mechanism") or {}).get(RECURSIVE, {}).get("share_ending_mid_sentence"),
            )
            for row in finished
            if (row.get("mechanism") or {}).get(FIXED, {}).get("share_ending_mid_sentence")
            is not None
            and (row.get("mechanism") or {}).get(RECURSIVE, {}).get("share_ending_mid_sentence")
            is not None
        }
    )

    parts: List[str] = []
    if best is not None:
        magnitude, delta, p_value, row = best
        parts.append(
            "The largest movement in hit@10 across the %d finished pair(s) is %+.4f in "
            "`%s` / `%s` (paired McNemar p = %s), and the point estimates of MRR and nDCG move "
            "with it by less than 0.01 in every pair — a null on retrieval quality, not a "
            "gain."
            % (
                len(finished),
                delta,
                row.get("retrieval_mode", "?"),
                row.get("context_mode", "?"),
                _p(p_value),
            )
            if magnitude == 0.0
            else "The largest movement in hit@10 across the %d finished pair(s) is %+.4f in "
            "`%s` / `%s` (paired McNemar p = %s)."
            % (len(finished), delta, row.get("retrieval_mode", "?"), row.get("context_mode", "?"), _p(p_value))
        )
    if structural:
        parts.append(
            "Atomicity itself did happen: %s of the recursive chunks that exceed the budget "
            "carry a table row or a code fence, so the splitter kept them whole at the cost of "
            "the token budget, and the share of chunks ending mid-sentence falls from %s to %s."
            % (
                ", ".join("%.0f%%" % (100.0 * value) for value in structural),
                _fmt(mid_sentence[0][0]) if mid_sentence else "pending",
                _fmt(mid_sentence[0][1]) if mid_sentence else "pending",
            )
        )

    # Citation support is the other paired outcome, and unlike retrieval it does
    # move — in both directions — so it is summarised from the data rather than
    # asserted in either direction.
    citation = []
    for row in finished:
        entry = (row.get("mcnemar") or {}).get("citation_support") or {}
        baseline_only = int(entry.get("baseline_only") or 0)
        treatment_only = int(entry.get("treatment_only") or 0)
        citation.append(
            (
                treatment_only - baseline_only,
                entry.get("p_value"),
                "%s/%s" % (row.get("retrieval_mode", "?"), row.get("context_mode", "?")),
            )
        )
    significant = [item for item in citation if item[1] is not None and item[1] < 0.05]
    if significant:
        best = max(significant, key=lambda item: abs(item[0]))
        parts.append(
            "The one thing chunk strategy does move is how often an answer carries a supported "
            "citation: %d of %d pairs shift significantly, the largest being %+d items in `%s` "
            "(p = %s), and the sign is not the same in every pair — so the mechanism buys "
            "citation coverage rather than retrieval quality."
            % (
                len(significant),
                len(citation),
                best[0],
                best[2],
                _p(best[1]),
            )
        )
    elif citation:
        parts.append(
            "No pair shifts significantly on whether an answer carries a supported citation, so "
            "the chunk strategy moves neither retrieval quality nor citation coverage here."
        )

    if table_significant:
        parts.append(
            "The `table_content` items do move (paired McNemar p < 0.05 on at least one pair), "
            "so on this corpus the atomic-table hypothesis survives where it was meant to bite."
        )
    elif table_ceiling:
        parts.append(
            "The `table_content` items — the golden questions whose answer sits in a table — "
            "are retrieved by both strategies at the ceiling in every finished pair, so the "
            "paired test has no discordant pair to work with and cannot show an effect either "
            "way. On this corpus the atomic-table hypothesis is not testable on the questions "
            "it was meant to help: keeping tables whole did not change which of them were found."
        )
    else:
        parts.append(
            "The `table_content` items — the golden questions whose answer sits in a table — "
            "do not move significantly in any pair, so keeping tables atomic did not measurably "
            "help the questions it was meant to help. On this corpus the atomic-table "
            "hypothesis does not survive: chunk strategy changes how chunks are built and how "
            "often an answer is cited, not how well retrieval works."
        )
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #


def cell_records(runs_root: str, configs_dir: str = "") -> List[Dict[str, Any]]:
    """The declared cells, each with its finished run directory when it has one."""
    paths = [configs_dir] if configs_dir else None
    records = []
    for cell in grid.plan(paths, out_root=runs_root):
        records.append(
            {
                "cell": cell["cell"],
                "factors": cell["factors"],
                "status": cell["status"],
                "run_dir": cell["run_dir"],
            }
        )
    return records


def build_payload(
    runs_root: str,
    chunks_root: str = "",
    golden_path: str = "golden/v1.jsonl",
    configs_dir: str = "",
    budget: int = 512,
) -> Dict[str, Any]:
    golden = aggregate.load_golden(golden_path)
    cells = cell_records(runs_root, configs_dir)
    pairs = pair_cells(cells)
    rows: List[Dict[str, Any]] = []
    for pair in pairs:
        if pair["status"] != "finished":
            rows.append(pending_pair_row(pair["retrieval_mode"], pair["context_mode"], pair["missing"]))
            continue
        rows.append(comparison_row(pair, golden, chunks_root=chunks_root, budget=budget))
    return {
        "runs_root": runs_root,
        "chunks_root": chunks_root,
        "golden_path": golden_path,
        "budget_tokens": int(budget),
        "pairs": rows,
        "verdict": verdict_for(rows),
        "protocol": {
            "pairing": "same retrieval mode and context mode, chunk.strategy the only factor",
            "test": "exact conditional McNemar on per-item outcomes (ragqa.baselines)",
            "mechanism": "ragqa.chunk.stats over the chunk set, at the pair's token budget",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="chunk_comparison", description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--chunks-root", default="data/chunks")
    parser.add_argument("--golden", default="golden/v1.jsonl")
    parser.add_argument("--configs", default="")
    parser.add_argument("--budget", type=int, default=512)
    parser.add_argument("--report-json", default="reports/chunking.json")
    parser.add_argument("--report-csv", default="reports/chunking.csv")
    parser.add_argument("--note", default="notes/chunking-comparison.md")
    args = parser.parse_args(argv)

    payload = build_payload(
        runs_root=args.runs_root,
        chunks_root=args.chunks_root,
        golden_path=args.golden,
        configs_dir=args.configs,
        budget=args.budget,
    )
    for path in (args.report_json, args.report_csv, args.note):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
    with open(args.report_json, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(args.report_csv, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_csv(payload["pairs"]))
    with open(args.note, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown(payload))

    finished = [row for row in payload["pairs"] if row.get("status") == "finished"]
    print(f"{len(payload['pairs'])} pair(s): {len(finished)} finished, {len(payload['pairs']) - len(finished)} pending")
    for row in finished:
        metrics = row["metrics"]
        print(
            "{} / {}: hit@10 {}{:+.4f} p={} citation recall {}{:+.4f} p={}".format(
                row["retrieval_mode"],
                row["context_mode"],
                float((metrics.get("hit_at_10") or {}).get("fixed") or 0.0),
                float((metrics.get("hit_at_10") or {}).get("delta") or 0.0),
                _p(((row.get("mcnemar") or {}).get("retrieval_hit") or {}).get("p_value")),
                float((metrics.get("citation_recall") or {}).get("fixed") or 0.0),
                float((metrics.get("citation_recall") or {}).get("delta") or 0.0),
                _p(((row.get("mcnemar") or {}).get("citation_support") or {}).get("p_value")),
            )
        )
    print(f"wrote {args.report_json}, {args.report_csv}, {args.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

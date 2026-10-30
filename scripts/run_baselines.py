"""Run exactly the four baseline cells of ticket 14, or say what would run.

    python scripts/run_baselines.py --dry-run
    python scripts/run_baselines.py                       # the four cells, for real
    python scripts/run_baselines.py --report --reference-dir runs/<ref-run-id>

This is a thin driver over `ragqa.run.execute`, which stays the only thing that
writes a run directory: a baseline that took a different path to its numbers
would not be comparable with the cells it is compared against.

`--dry-run` is the default posture for this ticket: it loads the four
configurations, counts the golden items, projects the model calls and prints the
resume state, and it touches neither the network nor the run root. It refuses to
spend money even when a key is present.

Resume semantics are by metrics file, not by intent: a cell whose run directory
already holds `metrics.json` and whose configuration matches is skipped. A run
that died mid-flight leaves no directory behind (`ragqa.run` deletes it), so
"present" and "measured" cannot disagree.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import baselines, config as config_mod  # noqa: E402
from ragqa.contract import git_state  # noqa: E402
from ragqa.llm import LLMError  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join("configs", "baselines")

# Exactly the four cells this ticket owns, in the order the report reads them.
CELLS: Tuple[Tuple[str, str], ...] = (
    ("closed-book", os.path.join(CONFIG_DIR, "closed-book.yaml")),
    ("long-context", os.path.join(CONFIG_DIR, "long-context.yaml")),
    ("embed-minilm", os.path.join(CONFIG_DIR, "embed-minilm.yaml")),
    ("gen-cheap", os.path.join(CONFIG_DIR, "gen-cheap.yaml")),
)

REFERENCE_RUN_NAME = "grid-recursive_parent_child-rerank-plain"

# The four cells are compared against the design's reference point, which is the
# grid cell `recursive_parent_child / rerank / plain`. It already answers the same
# 60-item golden set the baselines use, so `--with-reference` only has to rename it
# -- and comparing against anything else (the older `configs/ctx-plain.yaml`, say,
# whose generation budget and abstention threshold are different) would put a
# second factor in every baseline row.
REFERENCE_NAME = "baseline-reference"
REFERENCE_SOURCE = os.path.join(
    "configs", "grid", "cell-recursive_parent_child-rerank-plain.yaml"
)

# ADR-0005 fixes the golden set at 60 items, 40 of them answerable. Used to
# project the call count while golden/v1.jsonl is not on the branch yet, and
# always labelled as an assumption when it is.
EXPECTED_GOLDEN = (60, 40)


def golden_size(path: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """(items, answerable) in a golden set, or (None, None) if it is not there."""
    if not path:
        return None, None
    full = path if os.path.isabs(path) else os.path.join(REPO, path)
    if not os.path.exists(full):
        return None, None
    import json

    items = 0
    answerable = 0
    with open(full, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            items += 1
            if record.get("answerable", True):
                answerable += 1
    return items, answerable


def latest_run(root: str, run_name: str) -> Optional[str]:
    """Newest run directory for a run name, requiring a metrics file."""
    if not os.path.isdir(root):
        return None
    found = None
    for entry in sorted(os.listdir(root)):
        if not entry.startswith(f"{run_name}-"):
            continue
        path = os.path.join(root, entry)
        if os.path.isfile(os.path.join(path, "metrics.json")):
            found = path
    return found


# --------------------------------------------------------------------------- #
# what the long-context window would cost, measured without calling a model
# --------------------------------------------------------------------------- #

# Caps the note reports: the reference window, the chosen window, and one high
# enough to hold this corpus's largest document whole.
WINDOW_CAPS = (12000, 20000, 70000)
USD_CNY = 6.67


def measure_window(
    run_dir: str,
    out_path: str,
    corpus_path: Optional[str] = None,
    caps=WINDOW_CAPS,
) -> Dict[str, Any]:
    """Prompt shapes and their projected cost, from one finished run.

    Nothing is generated. The prompt text for each shape is built by the real
    `LLMGenerator._messages`, so the char counts are what a model would actually
    be sent, and tokens are that times a chars->tokens rate measured on the run's
    own `tokens_in`. The reference cell's shape acts as the calibration: the same
    projection applied to it should land near its measured token count.
    """
    import json
    import statistics

    from ragqa import generate

    def rows(path):
        return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]

    def percentile(values, fraction):
        ordered = sorted(values)
        return ordered[int(round(fraction * (len(ordered) - 1)))] if ordered else 0

    config = json.load(open(os.path.join(run_dir, "config.json"), encoding="utf-8"))
    corpus_source = corpus_path or config["corpus"]["source"]
    if not os.path.isabs(corpus_source):
        corpus_source = os.path.join(REPO, corpus_source)
    price_in = float(config["llm"]["price_in_usd_per_mtok"])
    price_out = float(config["llm"]["price_out_usd_per_mtok"])

    docs = {d["doc_id"]: d for d in rows(corpus_source)}
    chunks = {c["chunk_id"]: c for c in rows(os.path.join(run_dir, "chunks.jsonl"))}
    predictions = rows(os.path.join(run_dir, "predictions.jsonl"))
    golden_path = config["golden"]["items_path"]
    if not os.path.isabs(golden_path):
        golden_path = os.path.join(REPO, golden_path)
    items = {it["id"]: it for it in rows(golden_path)}
    context_chunks = int(config["llm"]["context_chunks"])

    generator = generate.LLMGenerator(None, model="dry", context_chunks=context_chunks)
    per_item = []
    for prediction in predictions:
        item = items[prediction["item_id"]]
        hits = []
        for hit in prediction["retrieved"][:context_chunks]:
            chunk = chunks[hit["chunk_id"]]
            hits.append(
                {
                    "chunk_id": hit["chunk_id"],
                    "doc_id": hit["doc_id"],
                    "rank": hit["rank"],
                    "text": chunk["text"],
                }
            )
        top_doc_id = prediction["retrieved"][0]["doc_id"] if prediction["retrieved"] else ""
        doc_text = docs[top_doc_id]["text"] if top_doc_id else ""
        entry = {
            "item_id": prediction["item_id"],
            "answerable": prediction["answerable"],
            "top_doc_id": top_doc_id,
            "top_doc_chars": len(doc_text),
            "rag_prompt_chars": sum(
                len(message["content"]) for message in generator._messages(item, hits, "")
            ),
            "closed_book_prompt_chars": sum(
                len(message["content"]) for message in generator._messages(item, [], "")
            ),
            "tokens_in_measured": prediction["tokens_in"],
            "tokens_out_measured": prediction["tokens_out"],
            "windows": {},
        }
        for cap in caps:
            entry["windows"][str(cap)] = {
                "context_chars": min(len(doc_text), cap),
                "truncated": len(doc_text) > cap,
                "prompt_chars": sum(
                    len(message["content"])
                    for message in generator._messages(item, [], doc_text[:cap])
                ),
            }
        per_item.append(entry)

    # Median tokens-per-char. Items whose tokens_in covers the corrective retry in
    # generate.py sit at roughly twice the rate and would drag a mean upward.
    ratios = sorted(e["tokens_in_measured"] / e["rag_prompt_chars"] for e in per_item)
    median_ratio = statistics.median(ratios)
    outliers = [
        e["item_id"]
        for e in per_item
        if e["tokens_in_measured"] / e["rag_prompt_chars"] > 1.5 * median_ratio
    ]

    n = len(per_item)
    doc_lengths = [len(d["text"]) for d in docs.values()]
    longest = sorted(docs.values(), key=lambda d: -len(d["text"]))[:3]
    tokens_out_mean = round(statistics.fmean(e["tokens_out_measured"] for e in per_item), 1)

    summary: Dict[str, Any] = {
        "source_run": os.path.basename(run_dir.rstrip("/\\")),
        "source_corpus": corpus_source,
        "price_in_usd_per_mtok": price_in,
        "price_out_usd_per_mtok": price_out,
        "corpus": {
            "documents": len(doc_lengths),
            "total_chars": sum(doc_lengths),
            "mean_chars": round(statistics.fmean(doc_lengths), 1),
            "p50": percentile(doc_lengths, 0.50),
            "p90": percentile(doc_lengths, 0.90),
            "p95": percentile(doc_lengths, 0.95),
            "p99": percentile(doc_lengths, 0.99),
            "max": max(doc_lengths),
            "longest": [{"doc_id": d["doc_id"], "chars": len(d["text"])} for d in longest],
        },
        "items": n,
        "answerable": sum(1 for e in per_item if e["answerable"]),
        "tokens_per_char": round(median_ratio, 6),
        "chars_per_token": round(1 / median_ratio, 3),
        "ratio_range": [round(ratios[0], 6), round(ratios[-1], 6)],
        "retry_outlier_items": outliers,
        "outlier_note": "tokens_in covers two calls (corrective retry), not a longer prompt",
        "top_doc_chars": {
            "min": min(e["top_doc_chars"] for e in per_item),
            "p50": percentile([e["top_doc_chars"] for e in per_item], 0.50),
            "p95": percentile([e["top_doc_chars"] for e in per_item], 0.95),
            "max": max(e["top_doc_chars"] for e in per_item),
        },
        "measured_tokens_out_mean": tokens_out_mean,
        "measured_tokens_in_mean": round(
            statistics.fmean(e["tokens_in_measured"] for e in per_item), 1
        ),
        "shapes": {},
        "per_item": per_item,
    }

    shapes = {
        "retrieval_k10_8chunks": [e["rag_prompt_chars"] for e in per_item],
        "closed_book": [e["closed_book_prompt_chars"] for e in per_item],
    }
    for cap in caps:
        shapes[f"long_context_{cap}"] = [e["windows"][str(cap)]["prompt_chars"] for e in per_item]

    for name, prompt_chars in shapes.items():
        tokens_in = [chars * median_ratio for chars in prompt_chars]
        usd = sum((tokens * price_in + tokens_out_mean * price_out) / 1e6 for tokens in tokens_in)
        summary["shapes"][name] = {
            "prompt_chars_mean": round(statistics.fmean(prompt_chars), 1),
            "prompt_tokens_mean": round(statistics.fmean(tokens_in), 1),
            "prompt_tokens_total": round(sum(tokens_in), 1),
            "usd_for_these_items": round(usd, 6),
            "cny_per_1k_questions": round(usd * USD_CNY * (1000.0 / n), 4),
        }
        if name.startswith("long_context_"):
            cap = int(name.rsplit("_", 1)[1])
            whole = sum(1 for e in per_item if not e["windows"][str(cap)]["truncated"])
            summary["shapes"][name]["items_full"] = whole
            summary["shapes"][name]["items_truncated"] = n - whole

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return summary


def reference_config(golden_path: str):
    """The reference cell, renamed so its run directory says what it is used for.

    Derived rather than copied so the two cells cannot drift: the only keys that
    move are the run name and the golden set, both identity keys for the purpose
    of a single-variable comparison (ADR-0003).
    """
    cfg = config_mod.load(os.path.join(REPO, REFERENCE_SOURCE))
    flat = dict(cfg.as_dict())
    flat["run.name"] = REFERENCE_NAME
    flat["golden.items_path"] = golden_path
    return config_mod.Config(flat)


def plan(
    out_root: str,
    items_limit: Optional[int],
    only: Optional[List[str]],
    with_reference: bool = False,
) -> List[Dict[str, Any]]:
    rows = []
    cells = list(CELLS)
    if with_reference:
        cells.insert(0, (REFERENCE_NAME, f"{REFERENCE_SOURCE} (renamed for the comparison)"))
    for stem, relative in cells:
        if only and stem not in only and not (with_reference and stem == REFERENCE_NAME):
            continue
        if stem == REFERENCE_NAME:
            golden = config_mod.load(os.path.join(REPO, CELLS[0][1]))["golden.items_path"]
            cfg = reference_config(golden)
        else:
            cfg = config_mod.load(os.path.join(REPO, relative))
        total, answerable = golden_size(cfg["golden.items_path"])
        assumed = total is None
        if assumed:
            total, answerable = EXPECTED_GOLDEN
        if items_limit:
            total = min(total, items_limit)
            answerable = min(answerable, items_limit)
        existing = baselines.completed_run(out_root, cfg)
        extra = []
        if int(cfg["retrieval.hops"]) > 1:
            extra.append("query rewrite per item")
        if cfg["judge.enabled"]:
            extra.append("one judge call per claim")
        rows.append(
            {
                "cell": stem,
                "config": relative,
                "items": total,
                "answerable": answerable,
                "assumed": assumed,
                "generation_calls": total,
                "extra_calls": extra,
                "existing": existing,
            }
        )
    return rows


def print_plan(rows: List[Dict[str, Any]], out_root: str) -> int:
    print("dry-run: no model is called, no run directory is written, nothing is spent")
    print(f"run root: {out_root}")
    print("")
    header = "{:<18} {:<56} {:>6} {:>5} {:>7}  {}"
    print(header.format("cell", "config", "items", "ans", "calls", "state"))
    projected = 0
    assumed_any = False
    for row in rows:
        mark = "*" if row["assumed"] else ""
        assumed_any = assumed_any or row["assumed"]
        items = f"{row['items']}{mark}"
        answerable = f"{row['answerable']}{mark}"
        calls = f"{row['generation_calls']}{mark}"
        projected += row["generation_calls"]
        state = f"measured: {os.path.basename(row['existing'])}" if row["existing"] else "pending"
        print(
            header.format(row["cell"], row["config"], items, answerable, calls, state)
        )
        if row["extra_calls"]:
            print(f"{'':<18} extra calls per item: {', '.join(row['extra_calls'])}")

    print("")
    if assumed_any:
        print(
            "* assumed: the golden set named by the config is not on disk. ADR-0005 "
            f"fixes it at {EXPECTED_GOLDEN[0]} items ({EXPECTED_GOLDEN[1]} answerable); "
            "the count becomes measured as soon as golden/v1.jsonl lands."
        )
    print(f"Projected generation calls: {projected} ({len(rows)} cells x items)")

    print("")
    has_reference = any(row["cell"] == REFERENCE_NAME for row in rows)
    if has_reference:
        print(
            "The reference row is configs/ctx-plain.yaml renamed and retargeted at this "
            "golden set; it exists so the four baselines have something to pair against."
        )
    else:
        print(
            "The comparison needs a reference cell on the same golden items. Without "
            "--with-reference this runner executes exactly the four baselines, so pass it "
            "when building a table, or point --report at a run made from configs/ctx-plain.yaml."
        )
    return 0


def run_cells(
    out_root: str,
    items_limit: Optional[int],
    only: Optional[List[str]],
    force: bool,
    with_reference: bool = False,
) -> int:
    from ragqa.run import execute

    cells = list(CELLS)
    if with_reference:
        cells.insert(0, (REFERENCE_NAME, f"{REFERENCE_SOURCE} (renamed for the comparison)"))

    results = []
    for stem, relative in cells:
        if only and stem not in only and not (with_reference and stem == REFERENCE_NAME):
            continue
        if stem == REFERENCE_NAME:
            golden = config_mod.load(os.path.join(REPO, CELLS[0][1]))["golden.items_path"]
            cfg = reference_config(golden)
        else:
            cfg = config_mod.load(os.path.join(REPO, relative))
        if items_limit:
            cfg = config_mod.Config({**cfg.as_dict(), "golden.limit": int(items_limit)})

        existing = baselines.completed_run(out_root, cfg)
        if existing and not force:
            print(f"skip {stem}: already measured in {os.path.basename(existing)}")
            results.append(existing)
            continue

        print(f"run  {stem}: {relative}")
        try:
            result = execute(cfg, out_root)
        except LLMError as error:
            print(f"generation unavailable: {error}", file=sys.stderr)
            print(
                "the pipeline left no run directory behind (ADR-0003); re-run once "
                "the gateway is reachable",
                file=sys.stderr,
            )
            return 4
        metrics = result["metrics"]
        print(
            "     {run}\n"
            "     hit@{k}={hit} citations P={p} R={r} over-abstain={o} CNY/1k={c}".format(
                run=result["run_id"],
                k=metrics["retrieval"]["k"],
                hit=metrics["retrieval"]["hit_rate"],
                p=metrics["citations"]["citation_precision"],
                r=metrics["citations"]["citation_recall"],
                o=metrics["abstention"]["over_abstain_rate"],
                c=metrics["system"].get("cost_per_1k_questions_cny"),
            )
        )
        results.append(result["run_dir"])

    if not results:
        print("nothing ran", file=sys.stderr)
        return 1
    return 0


def build_report(out_root: str, reports_dir: str, reference_dir: Optional[str]) -> int:
    runs: List[str] = []
    reference = (
        reference_dir
        or latest_run(out_root, REFERENCE_NAME)
        or latest_run(out_root, REFERENCE_RUN_NAME)
    )
    if not reference:
        print(
            "no reference cell found. Pass --reference-dir runs/<run-id>: a baseline "
            "compared with nothing is not a comparison.",
            file=sys.stderr,
        )
        return 2
    runs.append(reference)
    for stem, _ in CELLS:
        path = latest_run(out_root, f"baseline-{stem}")
        if path:
            runs.append(path)
        else:
            print(f"note: {stem} has not been run, its row will be absent", file=sys.stderr)
    if len(runs) < 2:
        print("only the reference cell exists; nothing to compare", file=sys.stderr)
        return 2

    written = baselines.report(runs, reports_dir, reference=reference)
    print(f"wrote {written['markdown']}")
    print(f"wrote {written['json']}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_baselines",
        description="Run the four ticket-14 baseline cells (closed book, long context, "
        "smaller embedder, cheaper generator) and nothing else.",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, spend nothing")
    parser.add_argument("--out", default=None, help="run output root (default: run.out_root)")
    parser.add_argument("--items", type=int, default=None, help="truncate the golden set")
    parser.add_argument("--only", nargs="*", default=None, help="restrict to these cell names")
    parser.add_argument("--force", action="store_true", help="re-run a cell that is already measured")
    parser.add_argument("--allow-dirty", action="store_true", help="run on a dirty git tree")
    parser.add_argument("--report", action="store_true", help="build reports/baselines/table.*")
    parser.add_argument("--reference-dir", default=None, help="reference run directory for --report")
    parser.add_argument("--reports-dir", default=os.path.join("reports", "baselines"))
    parser.add_argument(
        "--measure-window",
        metavar="RUN_DIR",
        default=None,
        help="regenerate reports/baselines/window-cost.json from a finished run; calls no model",
    )
    parser.add_argument("--corpus", default=None, help="corpus path for --measure-window")
    parser.add_argument(
        "--with-reference",
        action="store_true",
        help="also run the reference cell (configs/ctx-plain.yaml, retargeted at the "
        "baselines' golden set) so the table has something to pair against; without "
        "the flag this runner executes exactly the four baselines",
    )
    args = parser.parse_args(argv)

    out_root = args.out or "runs"

    if args.measure_window:
        summary = measure_window(
            args.measure_window,
            os.path.join(args.reports_dir, "window-cost.json"),
            corpus_path=args.corpus,
        )
        print(
            "wrote {path} from {run}: {n} items, {chars} chars/token".format(
                path=os.path.join(args.reports_dir, "window-cost.json"),
                run=summary["source_run"],
                n=summary["items"],
                chars=summary["chars_per_token"],
            )
        )
        for name, shape in sorted(summary["shapes"].items()):
            print(
                "  {name:<24} prompt tokens {tokens:>8} CNY/1k {cny:>7}".format(
                    name=name,
                    tokens=shape["prompt_tokens_mean"],
                    cny=shape["cny_per_1k_questions"],
                )
            )
        return 0

    if args.report:
        return build_report(out_root, args.reports_dir, args.reference_dir)

    if args.dry_run:
        return print_plan(
            plan(out_root, args.items, args.only, with_reference=args.with_reference),
            out_root,
        )

    state = git_state(REPO)
    if state["dirty"] and not args.allow_dirty:
        print(
            f"refusing to run: working tree is dirty ({state['sha']}). Commit or pass "
            "--allow-dirty.",
            file=sys.stderr,
        )
        return 2

    return run_cells(
        out_root, args.items, args.only, args.force, with_reference=args.with_reference
    )


if __name__ == "__main__":
    raise SystemExit(main())

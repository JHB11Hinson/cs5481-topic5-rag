"""Reproduce the ticket-10 judge calibration from stored artifacts.

Three inputs, no notebook: the run directories (for the chunk text each claim
cites), the hand-labelled claim set, and the gateway credentials in `.env`.
Everything a model produced is cached in `notes/judge-calibration.verdicts.json`,
so a second run makes no calls and prints the same tables; `--refresh-llm` re-asks
the hosted judge.

    python scripts/calibrate_judges.py                 # NLI + hosted judge
    python scripts/calibrate_judges.py --no-llm        # NLI only, no network
    python scripts/calibrate_judges.py --refresh-llm   # re-ask the hosted judge

Outputs, all under `notes/`: the verdict cache, the NLI x judge confusion table as
CSV, a metrics fragment carrying `grounding.judge_confusion` plus the judge's call
count and cost, and the marked table block inside `judge-calibration.md`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# A Windows console defaults to a legacy code page that cannot encode the report
# characters this script prints, and a failed print would look like a failed run.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from ragqa import config as config_mod  # noqa: E402
from ragqa import judges, verify  # noqa: E402
from ragqa.corpus import read_jsonl  # noqa: E402

DEFAULT_RUNS_ROOT = r"D:\DE Project\Project\runs"
LABELS = "notes/judge-calibration.json"
VERDICTS = "notes/judge-calibration.verdicts.json"
CSV_PATH = "notes/judge-confusion.csv"
METRICS = "notes/judge-calibration.metrics.json"
NOTE = "notes/judge-calibration.md"
BLOCK_BEGIN = "<!-- BEGIN GENERATED: judge calibration tables -->"
BLOCK_END = "<!-- END GENERATED: judge calibration tables -->"
USD_TO_CNY = 6.67  # the rate run.py uses when it reports cost_cny


def load_labels(path: str = LABELS) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload["claims"]
    for row in rows:
        row["human_label"] = bool(row["human_label"])
        for field in ("claim_id", "chunk_id", "doc_id", "claim_text", "source_run"):
            if not row.get(field):
                raise ValueError(f"{path}: row {row.get('claim_id')!r} has no {field}")
    return payload


def chunk_index(runs_root: str, rows: List[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
    """Only the chunks the labelled rows cite, read once per run directory."""
    wanted: Dict[str, set] = {}
    for row in rows:
        wanted.setdefault(row["source_run"], set()).add(row["chunk_id"])
    index: Dict[tuple, Dict[str, Any]] = {}
    for run, chunk_ids in wanted.items():
        path = os.path.join(runs_root, run, "chunks.jsonl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} - point --runs-root at the main checkout")
        for row in read_jsonl(path):
            if row["chunk_id"] in chunk_ids:
                index[(run, row["chunk_id"])] = row
    missing = {
        (row["source_run"], row["chunk_id"])
        for row in rows
        if (row["source_run"], row["chunk_id"]) not in index
    }
    if missing:
        raise ValueError(f"chunk(s) missing from the run directories: {sorted(missing)}")
    return index


def load_cache(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_cache(path: str, cache: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(cache, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def judge_rows(cfg, payload, index, verdicts_path: str, use_llm: bool,
               refresh_nli: bool, refresh_llm: bool):
    """Judge every labelled row through the production plumbing, caching verdicts."""
    nli = judges.NLIJudge(
        model_id=cfg["judge.nli_model"], threshold=float(cfg["judge.nli_threshold"])
    )
    llm = None
    client = None
    if use_llm:
        from ragqa.llm import LLMClient

        model = cfg["judge.llm_model"] or cfg["llm.model_judge"]
        client = LLMClient(
            base_url=cfg["llm.base_url"],
            cache_path=cfg["llm.cache_path"] + ".judge",
            timeout=int(cfg["llm.timeout"]),
            temperature=0.0,
            session_header=cfg["llm.session_header"],
            session_id=cfg["llm.session_id"],
        )
        # The judge is asked to deliberate — it is the "reference" layer — and a
        # 700-token budget is what keeps the model's thinking channel from eating
        # the whole allowance and returning empty content.
        llm = judges.LLMJudge(client, model=model, max_chars=int(cfg["judge.llm_max_chars"]))
    stack = judges.SupportJudges(nli=nli, llm=llm)

    cache = load_cache(verdicts_path)
    computed = {"nli": 0, "llm": 0}
    for row in payload["claims"]:
        entry = cache.get(row["claim_id"]) or {}
        # A layer that was switched off last time leaves no verdict behind, so it
        # is recomputed rather than mistaken for "already judged".
        needs_nli = refresh_nli or not entry.get("nli")
        needs_llm = llm is not None and (refresh_llm or not entry.get("llm"))
        if not (needs_nli or needs_llm):
            continue

        chunk = index[(row["source_run"], row["chunk_id"])]
        retrieved = [
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "rank": 1,
                "score": 1.0,
                "text": chunk["text"],
            }
        ]
        claim = {
            "claim_id": row["claim_id"],
            "chunk_id": row["chunk_id"],
            "doc_id": row["doc_id"],
            "text": row["claim_text"],
            "quote": row.get("quote", ""),
        }
        verdict = verify.check_claims([claim], retrieved)[0]
        stack.judge_claim(claim, verdict, retrieved)
        entry = {
            "claim_id": row["claim_id"],
            "containment_ok": bool(verdict.get("containment_ok")),
            "containment_error": verdict.get("error_class", ""),
            "nli": {
                "supported": verdict.get("nli_supported"),
                "label": verdict.get("nli_label"),
                "score": verdict.get("nli_score"),
            },
            "llm": (
                {
                    "supported": verdict.get("judge_supported"),
                    "reason": verdict.get("judge_reason", ""),
                    "tokens_in": int(verdict.get("judge_tokens_in", 0) or 0),
                    "tokens_out": int(verdict.get("judge_tokens_out", 0) or 0),
                }
                if verdict.get("judge_supported") is not None
                else None
            ),
            "nli_model": nli.model_id,
            "nli_threshold": float(nli.threshold),
            "llm_model": llm.model_id if llm is not None else "",
        }
        cache[row["claim_id"]] = entry
        computed["nli"] += 1
        if llm is not None:
            computed["llm"] += 1

    save_cache(verdicts_path, cache)
    stats = {
        "computed_rows": computed,
        "nli_stats": dict(nli.last_stats),
        "llm_stats": dict(llm.last_stats) if llm is not None else None,
    }
    return cache, stats, client


def spend(cache: Dict[str, Any]) -> Dict[str, int]:
    """Tokens behind the stored verdicts — what it cost to produce these numbers."""
    entries = [entry.get("llm") or {} for entry in cache.values()]
    return {
        "calls": sum(1 for entry in entries if entry),
        "tokens_in": sum(int(entry.get("tokens_in", 0) or 0) for entry in entries),
        "tokens_out": sum(int(entry.get("tokens_out", 0) or 0) for entry in entries),
        "nli_calls": sum(1 for entry in cache.values() if (entry.get("nli") or {}).get("score") is not None),
    }


def summarise(payload, cache) -> Dict[str, Any]:
    rows = payload["claims"]
    human = [row["human_label"] for row in rows]
    nli = [(cache.get(row["claim_id"]) or {}).get("nli", {}).get("supported") for row in rows]
    llm = [(cache.get(row["claim_id"]) or {}).get("llm") or {} for row in rows]
    llm_verdicts = [entry.get("supported") if entry else None for entry in llm]
    confusion = judges.confusion(
        [{"nli_supported": a, "judge_supported": b} for a, b in zip(nli, llm_verdicts)]
    )
    return {
        "rows": rows,
        "human": human,
        "nli": nli,
        "llm": llm_verdicts,
        "reasons": [entry.get("reason", "") if entry else "" for entry in llm],
        "nli_score": judges.score_against_human(human, nli),
        "llm_score": judges.score_against_human(human, llm_verdicts),
        "confusion": confusion,
    }


def _cell(value: Optional[bool]) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def _table_2x2(score: Dict[str, Any], label: str) -> List[str]:
    return [
        f"**{label}** — {score['n']} judged, {score['skipped']} not judged",
        "",
        "| | human: supported | human: unsupported |",
        "|---|---|---|",
        f"| **judge: supported** | {score['tp']} (TP) | {score['fp']} (FP) |",
        f"| **judge: unsupported** | {score['fn']} (FN) | {score['tn']} (TN) |",
        "",
    ]


def markdown_block(payload, summary, cost) -> str:
    rows = summary["rows"]
    lines: List[str] = [BLOCK_BEGIN, ""]
    lines += [
        "## The 30 labelled claims and what each layer said",
        "",
        "`yes` = supported, `no` = unsupported, `-` = layer was not asked (containment failed).",
        "",
        "| # | claim id | claim | human | NLI | judge | one-line justification |",
        "|---|---|---|---|---|---|---|",
    ]
    for number, row in enumerate(rows, start=1):
        lines.append(
            "| {n} | `{cid}` | {claim} | {human} | {nli} | {llm} | {why} |".format(
                n=number,
                cid=row["claim_id"],
                claim=row["claim_text"].replace("|", "\\|"),
                human=_cell(row["human_label"]),
                nli=_cell(summary["nli"][number - 1]),
                llm=_cell(summary["llm"][number - 1]),
                why=row["justification"].replace("|", "\\|"),
            )
        )
    lines += ["", "## Agreement with the hand labels", ""]
    lines += [
        "| layer | judged | raw agreement | precision | recall | Cohen's kappa |",
        "|---|---|---|---|---|---|",
    ]
    for label, score in (
        ("NLI cross-encoder", summary["nli_score"]),
        ("LLM judge", summary["llm_score"]),
    ):
        lines.append(
            f"| {label} | {score['n']} | {score['agreement']:.3f} | {score['precision']:.3f} "
            f"| {score['recall']:.3f} | {score['kappa']:.3f} |"
        )
    lines += ["", "## Confusion matrices", ""]
    lines += _table_2x2(summary["nli_score"], "NLI vs human")
    lines += _table_2x2(summary["llm_score"], "LLM judge vs human")
    grid = summary["confusion"]
    lines += [
        "## NLI x judge on the same claim",
        "",
        "| | judge: supported | judge: unsupported |",
        "|---|---|---|",
        f"| **NLI: supported** | {grid['both_supported']} | {grid['nli_only']} |",
        f"| **NLI: unsupported** | {grid['judge_only']} | {grid['neither']} |",
        "",
        f"The same grid is written to `{CSV_PATH}` for the report.",
        "",
        "## Cost and calls",
        "",
        "| item | value |",
        "|---|---|",
        f"| judge model | `{cost['judge_model']}` |",
        f"| judge verdicts stored (one call each) | {cost['llm_calls']} |",
        f"| judge tokens in / out | {cost['tokens_in']} / {cost['tokens_out']} |",
        f"| judge cost at configured prices | ${cost['usd']:.4f} / ¥{cost['cny']:.4f} |",
        f"| judge price in / out (USD per Mtok) | {cost['prices_usd_per_mtok']['in']} / "
        f"{cost['prices_usd_per_mtok']['out']} |",
        f"| NLI calls | {cost['nli_calls']} (local, free) |",
        f"| NLI threshold | {cost['threshold']} |",
        BLOCK_END,
    ]
    return "\n".join(lines)


def write_csv(path: str, summary) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table", "cell", "count"])
        grid = summary["confusion"]
        for cell in ("both_supported", "nli_only", "judge_only", "neither"):
            writer.writerow(["nli_x_judge", cell, grid[cell]])
        for label, score in (
            ("nli_vs_human", summary["nli_score"]),
            ("judge_vs_human", summary["llm_score"]),
        ):
            for cell in ("tp", "fp", "fn", "tn"):
                writer.writerow([label, cell, score[cell]])


def update_note(path: str, block: str) -> str:
    if not os.path.exists(path):
        return "skipped (no note yet)"
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if BLOCK_BEGIN not in text or BLOCK_END not in text:
        return "skipped (note has no generated block)"
    head, rest = text.split(BLOCK_BEGIN, 1)
    _, tail = rest.split(BLOCK_END, 1)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(head + block + tail)
    return "updated"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Judge calibration for ticket 10.")
    parser.add_argument("--labels", default=LABELS)
    parser.add_argument("--runs-root", default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--config", default="configs/real_llm.yaml")
    parser.add_argument("--verdicts", default=VERDICTS)
    parser.add_argument("--csv", default=CSV_PATH)
    parser.add_argument("--metrics", default=METRICS)
    parser.add_argument("--note", default=NOTE)
    parser.add_argument("--no-llm", action="store_true", help="NLI layer only; no network")
    parser.add_argument("--refresh-nli", action="store_true")
    parser.add_argument("--refresh-llm", action="store_true")
    args = parser.parse_args(argv)

    os.chdir(HERE)
    cfg = config_mod.load(args.config)
    payload = load_labels(args.labels)
    index = chunk_index(args.runs_root, payload["claims"])

    cache, stats, client = judge_rows(
        cfg, payload, index, args.verdicts, not args.no_llm, args.refresh_nli, args.refresh_llm
    )
    summary = summarise(payload, cache)

    price_in = float(cfg["llm.price_judge_in_usd_per_mtok"]) or float(
        cfg["llm.price_in_usd_per_mtok"]
    )
    price_out = float(cfg["llm.price_judge_out_usd_per_mtok"]) or float(
        cfg["llm.price_out_usd_per_mtok"]
    )
    usage = spend(cache)
    tokens_in = usage["tokens_in"]
    tokens_out = usage["tokens_out"]
    usd = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    cost = {
        "judge_model": (cfg["judge.llm_model"] or cfg["llm.model_judge"]) if not args.no_llm else "",
        "llm_calls": usage["calls"],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "usd": usd,
        "cny": usd * USD_TO_CNY,
        "nli_calls": usage["nli_calls"],
        "threshold": float(cfg["judge.nli_threshold"]),
        "prices_usd_per_mtok": {"in": price_in, "out": price_out},
    }

    for row, nli, verdict in zip(summary["rows"], summary["nli"], summary["llm"]):
        print(
            f"{row['claim_id']:8s} human={_cell(row['human_label']):3s} "
            f"nli={_cell(nli):3s} judge={_cell(verdict):3s} {row['claim_text'][:70]}"
        )
    print()
    for label, score in (("nli  ", summary["nli_score"]), ("judge", summary["llm_score"])):
        print(
            f"{label} n={score['n']} skipped={score['skipped']} agreement={score['agreement']} "
            f"precision={score['precision']} recall={score['recall']} kappa={score['kappa']}"
        )
    print(f"nli x judge {summary['confusion']}")
    print(
        f"judge calls={cost['llm_calls']} tokens={tokens_in}/{tokens_out} "
        f"cost=${usd:.4f} (CNY {usd * USD_TO_CNY:.4f}); nli calls={cost['nli_calls']}"
    )

    write_csv(args.csv, summary)
    metrics = {
        "calibration_set": len(payload["claims"]),
        "bar_kappa": payload.get("bar"),
        "nli": summary["nli_score"],
        "judge": summary["llm_score"],
        "grounding": {
            "claims": len(payload["claims"]),
            "judge_confusion": summary["confusion"],
        },
        "cost": cost,
    }
    with open(args.metrics, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"note block {update_note(args.note, markdown_block(payload, summary, cost))}")
    print(f"wrote {args.csv} and {args.metrics}")
    if client is not None:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



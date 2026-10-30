"""Answer correctness against the Golden QA Set's reference answers (ticket 18).

The report measures retrieval hit rate, MRR, nDCG, citation containment and
abstention. None of those is *answer correctness*: a retrieved chunk and a
supported citation say the system was grounded, not that its answer was right,
and the course brief asks for "retrieval hit rate **and** answer correctness"
(notes/report-factcheck.md §2 row 17). So this module adds the one measurement
the artifacts were missing, on the same 60-item Golden QA Set, using the
`reference_answer` each answerable item already carries.

`GLOSSARY.md` lists "correctness, accuracy" under *Avoid* for **Faithfulness**,
and that entry is about not confusing an answer's grounding with its truth. The
distinction is kept here rather than dissolved into the glossary's preferred
word: faithfulness is what `evaluate.py` reports (claims supported by the cited
chunks), answer correctness is what this module reports (does the generated
answer agree with the reference answer), and they can disagree in both
directions — a perfectly grounded answer to the wrong question is faithful and
incorrect.

Three numbers are reported per configuration and never folded together, because
they answer three different questions:

- accuracy over every answerable item: an abstention counts as not correct, so
  this is what a user asking a question of the system experiences;
- accuracy over the items the system chose to answer: abstentions leave the
  denominator, so this is the generator's accuracy when it commits;
- the abstention count itself, which is the only one of the three that says how
  much work the first two numbers are doing.

Abstentions are never sent to the judge: the outcome is already decided by the
generator's own contract, and a call cannot change a refusal into an answer.
That caps spend at one call per answerable item — 40 per configuration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

# The system message names the three fields it wants and the word "json": the
# gateway rejects `response_format: {"type": "json_object"}` unless the prompt
# contains it (ticket 18 briefing, and `docs/PROGRESS.md`), and a judge whose
# reply is reflowed prose would be an unparseable verdict on every item.
JUDGE_SYSTEM = (
    "You are a strict grader for a documentation question-answering system. You "
    "are given a QUESTION, the REFERENCE ANSWER from the documentation, and the "
    "GENERATED ANSWER the system produced. Decide whether the generated answer is "
    "correct: it must agree with the reference answer on every fact it states. A "
    "different wording, a shorter form, or extra correct detail is still correct; "
    "a missing value, a changed number, a changed default, a changed version, or a "
    "condition the reference does not state is incorrect. If the generated answer "
    "refuses or hedges instead of answering, it is incorrect. Reply with JSON "
    'only: {"correct": true|false, "reason": "<one short sentence>"}'
)

# Truncation bounds so one runaway answer cannot blow the prompt up: the longest
# reference answer in golden/v1.jsonl is under 400 characters, and no generated
# answer in the finished matrix runs past 4,000.
MAX_TEXT_CHARS = 2000

DEFAULT_JUDGE_TOKENS = 400


def build_messages(
    question: str,
    reference_answer: str,
    generated_answer: str,
    max_chars: int = MAX_TEXT_CHARS,
) -> List[Dict[str, str]]:
    """The two messages the judge is called with.

    Kept as a pure function so a test can read the prompt instead of trusting it:
    a judge that is not shown the reference answer cannot be measuring agreement
    with it.
    """
    body = (
        f"QUESTION:\n{str(question).strip()}\n\n"
        f"REFERENCE ANSWER:\n{str(reference_answer).strip()[:max_chars]}\n\n"
        f"GENERATED ANSWER:\n{str(generated_answer).strip()[:max_chars]}"
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": body},
    ]


def parse_reply(raw: str) -> Optional[Dict[str, Any]]:
    """A judge reply as `{"correct": bool, "reason": str}`, or None.

    `judges._parse` already knows how to dig JSON out of a fenced or chatty reply;
    this wraps it and then insists on the one key the verdict needs. Returning
    None — never `{"correct": False}` — is the whole point: an unparseable reply
    says nothing about the answer, and scoring it as wrong would quietly deflate
    every accuracy number by however often the judge rambles.
    """
    from .judges import _parse  # the one definition of "find the json in a reply"

    payload = _parse(raw)
    if payload is None or not isinstance(payload.get("correct"), bool):
        return None
    return {"correct": bool(payload["correct"]), "reason": str(payload.get("reason", ""))[:300]}


class CorrectnessJudge:
    """One call per answerable item: is the generated answer correct?

    The client is constructed with `reasoning_effort="none"` by the caller (see
    `scripts/score_correctness.py`), because this is mechanical work: at the
    default effort the thinking channel spends tokens that a one-word verdict does
    not need. `LLMClient` already caches every reply by content hash, so a second
    pass over the same configurations costs nothing and returns identical text.
    """

    def __init__(
        self,
        client,
        model: str,
        max_tokens: int = DEFAULT_JUDGE_TOKENS,
        max_chars: int = MAX_TEXT_CHARS,
    ):
        if not model:
            raise ValueError("CorrectnessJudge needs a model id")
        self.client = client
        self.model_id = model
        self.max_tokens = int(max_tokens)
        self.max_chars = int(max_chars)
        self.stats: Dict[str, int] = {
            "calls": 0,
            "correct": 0,
            "parse_failures": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def judge(self, question: str, reference_answer: str, generated_answer: str) -> Dict[str, Any]:
        messages = build_messages(question, reference_answer, generated_answer, self.max_chars)
        result = self.client.complete(self.model_id, messages, max_tokens=self.max_tokens)
        self.stats["calls"] += 1
        tokens_in = int(result.get("tokens_in", 0) or 0)
        tokens_out = int(result.get("tokens_out", 0) or 0)
        self.stats["tokens_in"] += tokens_in
        self.stats["tokens_out"] += tokens_out
        if result.get("cached"):
            self.stats["cache_hits"] += 1
        else:
            self.stats["cache_misses"] += 1
        payload = parse_reply(result.get("text", ""))
        if payload is None:
            self.stats["parse_failures"] += 1
            return {
                "correct": None,
                "reason": "judge reply was not parseable as a verdict",
                "parse_failure": True,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }
        if payload["correct"]:
            self.stats["correct"] += 1
        return {
            "correct": payload["correct"],
            "reason": payload["reason"],
            "parse_failure": False,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }


def judge_run(
    run_dir: str,
    golden: Dict[str, Dict[str, Any]],
    judge: CorrectnessJudge,
) -> List[Dict[str, Any]]:
    """One verdict per *answerable* item the run predicted.

    Near-miss items are skipped: they have no reference answer, so "is this
    correct" is not a question about them — whether the system abstained on them
    is `metrics.json`'s abstention recall, measured elsewhere. An abstention on an
    answerable item is recorded as not correct without spending a call: the
    generator already decided the answer, and no judge can turn a refusal into an
    answer.
    """
    from .corpus import read_jsonl

    predictions = read_jsonl(os.path.join(run_dir, "predictions.jsonl"))
    verdicts: List[Dict[str, Any]] = []
    for prediction in predictions:
        item_id = prediction.get("item_id", "")
        entry = golden.get(item_id) or {}
        reference = str(entry.get("reference_answer") or "")
        if not entry.get("answerable") or not reference:
            continue
        abstained = bool(prediction.get("abstained"))
        if abstained:
            verdicts.append(
                {
                    "item_id": item_id,
                    "answerable": True,
                    "abstained": True,
                    "judged": False,
                    "correct": False,
                    "reason": "the system abstained on an answerable item",
                    "parse_failure": False,
                }
            )
            continue
        outcome = judge.judge(
            str(entry.get("question") or prediction.get("question") or ""),
            reference,
            str(prediction.get("answer_text") or ""),
        )
        verdicts.append(
            {
                "item_id": item_id,
                "answerable": True,
                "abstained": False,
                "judged": True,
                "correct": outcome["correct"],
                "reason": outcome["reason"],
                "parse_failure": bool(outcome["parse_failure"]),
            }
        )
    verdicts.sort(key=lambda verdict: verdict["item_id"])
    return verdicts


def score_items(verdicts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The three numbers, computed from per-item verdicts and kept apart.

    Shares one numerator between the first two — an abstention is never correct —
    and differs only in the denominator, which is exactly the distinction between
    "what a user gets" and "what the generator gets when it commits". A verdict
    that could not be parsed is counted as not correct *and* reported as its own
    count, so a flaky judge shows up instead of quietly lowering the rate.
    """
    answerable = [v for v in verdicts if v.get("answerable", True)]
    answered = [v for v in answerable if not v.get("abstained")]
    correct = sum(1 for v in answerable if v.get("correct") is True)
    parse_failures = sum(1 for v in answerable if v.get("parse_failure"))
    total = len(answerable)

    def ratio(part: int, whole: int) -> Optional[float]:
        return round(part / whole, 4) if whole else None

    return {
        "answerable": total,
        "answered": len(answered),
        "abstentions": total - len(answered),
        "correct": correct,
        "parse_failures": parse_failures,
        "accuracy_all": ratio(correct, total),
        "accuracy_answered": ratio(correct, len(answered)),
    }


# --------------------------------------------------------------------------- #
# intervals, price
# --------------------------------------------------------------------------- #

BOOTSTRAP_SEED = 20261030
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_CONFIDENCE = 0.95
# The rate `scripts/calibrate_judges.py` and `run.py` use when they report CNY;
# a second rate would make the two money columns disagree.
USD_TO_CNY = 6.67


def cell_seed(cell: str) -> int:
    """A per-cell resampling seed, stable across runs and independent of order.

    Derived from the cell name the same way `aggregate._cell_seed` does it, so a
    cell's interval does not move when another cell finishes and lands in front of
    it in the loop.
    """
    import zlib

    return (BOOTSTRAP_SEED ^ zlib.crc32(cell.encode("utf-8"))) & 0x7FFFFFFF


def bootstrap_interval(
    values: Sequence[float],
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> Dict[str, Any]:
    """Percentile bootstrap over items for the mean of a 0/1 vector.

    Item is the resampling unit everywhere else in the report (`matrix.json`'s
    protocol says `resample_unit: item`), and the items are the independent draws
    — a claim is not.
    """
    from .aggregate import bootstrap_mean_ci  # one resampler, one definition of lo/hi

    summary = bootstrap_mean_ci(
        [float(value) for value in values],
        resamples=resamples,
        seed=seed,
        confidence=confidence,
    )
    return {
        "mean": summary["mean"],
        "lo": summary["lo"],
        "hi": summary["hi"],
        "n": summary["n"],
        "resamples": summary["resamples"],
        "seed": summary["seed"],
        "confidence": summary["confidence"],
    }


def judge_prices(cfg: Dict[str, Any]) -> Dict[str, float]:
    """USD per million tokens for the judge, with the generator's price fallback.

    `llm.price_judge_*` defaults to 0, which means "not priced separately"; the
    calibration artifact prices the judge at the generator's rates for that
    reason, and pricing it at zero here would report a free judge.
    """
    def pick(judge_key: str, fallback_key: str) -> float:
        return float(cfg.get(judge_key) or cfg.get(fallback_key) or 0.0)

    return {
        "in": pick("llm.price_judge_in_usd_per_mtok", "llm.price_in_usd_per_mtok"),
        "out": pick("llm.price_judge_out_usd_per_mtok", "llm.price_out_usd_per_mtok"),
    }


def judge_cost(tokens_in: int, tokens_out: int, prices: Dict[str, float]) -> Dict[str, float]:
    """What those tokens cost, in USD and in the CNY the report prints."""
    usd = int(tokens_in) / 1e6 * float(prices["in"]) + int(tokens_out) / 1e6 * float(prices["out"])
    return {"usd": round(usd, 6), "cny": round(usd * USD_TO_CNY, 6), "prices_usd_per_mtok": dict(prices)}


# --------------------------------------------------------------------------- #
# the table
# --------------------------------------------------------------------------- #

# One flat row per configuration, so the CSV and the JSON cannot disagree about
# what a row holds. A pending cell fills every number with None, which prints as
# an empty CSV cell: an unmeasured configuration is not a zero.
ROW_FIELDS = (
    "cell",
    "run_id",
    "status",
    "chunk_strategy",
    "retrieval_mode",
    "context_mode",
    "answerable",
    "answered",
    "abstentions",
    "correct",
    "parse_failures",
    "accuracy_all",
    "accuracy_all_lo",
    "accuracy_all_hi",
    "accuracy_answered",
    "accuracy_answered_lo",
    "accuracy_answered_hi",
    "judge_calls",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "cost_cny",
)

REGENERATE = (
    "python scripts/score_correctness.py --runs-root <runs root> "
    "--report-json reports/correctness.json --report-csv reports/correctness.csv "
    "--note notes/correctness.md"
)


def cell_row(
    cell: str,
    run_id: str,
    factors: Dict[str, str],
    verdicts: Sequence[Dict[str, Any]],
    judge_stats: Dict[str, Any],
    prices: Dict[str, float],
) -> Dict[str, Any]:
    """One configuration's row: the three numbers, their intervals, and the spend.

    The intervals are bootstrapped separately for the two denominators — over all
    answerable items and over the answered ones — because they are intervals for
    two different questions and a shared interval would blur exactly the
    distinction the table exists to show.
    """
    score = score_items(verdicts)
    every = [1.0 if verdict.get("correct") is True else 0.0 for verdict in verdicts]
    answered = [
        1.0 if verdict.get("correct") is True else 0.0
        for verdict in verdicts
        if not verdict.get("abstained")
    ]
    seed = cell_seed(cell)
    interval_all = bootstrap_interval(every, seed) if every else {}
    interval_answered = bootstrap_interval(answered, seed) if answered else {}
    tokens_in = int(judge_stats.get("tokens_in", 0) or 0)
    tokens_out = int(judge_stats.get("tokens_out", 0) or 0)
    cost = judge_cost(tokens_in, tokens_out, prices)

    row = {
        "cell": cell,
        "run_id": run_id,
        "status": "finished",
        "chunk_strategy": factors.get("chunk_strategy", ""),
        "retrieval_mode": factors.get("retrieval_mode", ""),
        "context_mode": factors.get("context_mode", ""),
        "answerable": score["answerable"],
        "answered": score["answered"],
        "abstentions": score["abstentions"],
        "correct": score["correct"],
        "parse_failures": score["parse_failures"],
        "accuracy_all": score["accuracy_all"],
        "accuracy_all_lo": interval_all.get("lo"),
        "accuracy_all_hi": interval_all.get("hi"),
        "accuracy_answered": score["accuracy_answered"],
        "accuracy_answered_lo": interval_answered.get("lo"),
        "accuracy_answered_hi": interval_answered.get("hi"),
        "judge_calls": int(judge_stats.get("calls", 0) or 0),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost["usd"],
        "cost_cny": cost["cny"],
    }
    return {field: row[field] for field in ROW_FIELDS}



def pending_row(cell: str, factors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """A configuration with no finished run: named, and measured by nothing."""
    row = {field: None for field in ROW_FIELDS}
    row.update({"cell": cell, "run_id": "", "status": "pending"})
    for key in ("chunk_strategy", "retrieval_mode", "context_mode"):
        row[key] = (factors or {}).get(key, "")
    return row


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_csv(rows: Sequence[Dict[str, Any]]) -> str:
    """The table as CSV, blanks for anything never measured."""
    lines = [",".join(ROW_FIELDS)]
    for row in rows:
        lines.append(",".join(_csv_value(row.get(field)) for field in ROW_FIELDS))
    return "\n".join(lines) + "\n"


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "pending"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_ci(mean: Any, lo: Any, hi: Any, digits: int = 4) -> str:
    if mean is None:
        return "pending"
    if lo is None or hi is None:
        return f"{_fmt(mean, digits)}"
    return f"{_fmt(mean, digits)} [{_fmt(lo, digits)}, {_fmt(hi, digits)}]"


def render_markdown(payload: Dict[str, Any]) -> str:
    """The note: what was measured, what is pending, and how to regenerate it."""
    protocol = payload.get("protocol") or {}
    totals = payload.get("totals") or {}
    rows = payload.get("cells") or []
    finished = [row for row in rows if row.get("status") == "finished"]
    pending = [row for row in rows if row.get("status") != "finished"]

    lines = [
        "# Answer correctness per configuration",
        "",
        "Generated by `scripts/score_correctness.py` from the finished run directories; do not "
        "edit by hand. The brief asks for retrieval hit rate **and** answer correctness "
        "(brief item 5, `notes/report-factcheck.md` §2 row 17); hit rate has lived in "
        "`reports/matrix.*` since ticket 15, and this is the correctness half.",
        "",
        "**What this measures.** For every *answerable* item of the Golden QA Set "
        "(`golden/v1.jsonl`, 40 of the 60), one hosted judge call (`%s`) is asked whether "
        "the generated answer agrees with the item's `reference_answer`. This is answer "
        "correctness against a reference, not faithfulness: faithfulness is whether the "
        "cited chunks support the claims, which `ragqa/evaluate.py` reports and which can be "
        "high while the answer is wrong. `GLOSSARY.md` files \"correctness\" under *Avoid* for "
        "**Faithfulness** to keep the two apart; the word is used here because that is the "
        "brief's word for this measurement."
        % protocol.get("judge_model", "?"),
        "",
        "**Three numbers, never one.**",
        "",
        "| column | question it answers |",
        "|---|---|",
        "| `accuracy_all` | of all 40 answerable items, how many did the system get right? "
        "An abstention counts as not correct. |",
        "| `accuracy_answered` | of the items the system chose to answer, how many are right? "
        "Abstentions leave the denominator. |",
        "| `abstentions` | how much work the first number's denominator is doing. |",
        "",
        "Both accuracies share a numerator (an abstention is never correct) and differ only in "
        "the denominator, which is why folding them into one number would hide exactly the "
        "trade-off the abstention threshold moves. Intervals are percentile bootstraps over "
        "items: %d resamples, seed %d (per cell, derived from the cell name so one cell's "
        "interval does not move when another finishes), %.0f%% confidence."
        % (
            int(protocol.get("bootstrap_resamples") or BOOTSTRAP_RESAMPLES),
            int(protocol.get("bootstrap_seed") or BOOTSTRAP_SEED),
            100.0 * float(protocol.get("bootstrap_confidence") or BOOTSTRAP_CONFIDENCE),
        ),
        "",
        "Abstentions are not sent to the judge: the generator already decided the answer, so a "
        "call could not change the verdict. That caps spend at one call per answerable item.",
        "",
        "## Per configuration",
        "",
        "| cell | run | accuracy (all 40) | accuracy (answered) | abstentions | correct/answered | judge calls | ¥ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        if row.get("status") != "finished":
            lines.append(
                "| `%s` | pending | pending | pending | pending | pending | — | — |"
                % row.get("cell", "?")
            )
            continue
        lines.append(
            "| `%s` | `%s` | %s | %s | %s of %s | %s/%s | %s | %s |"
            % (
                row.get("cell", "?"),
                row.get("run_id", ""),
                _fmt_ci(row.get("accuracy_all"), row.get("accuracy_all_lo"), row.get("accuracy_all_hi")),
                _fmt_ci(
                    row.get("accuracy_answered"),
                    row.get("accuracy_answered_lo"),
                    row.get("accuracy_answered_hi"),
                ),
                _fmt(row.get("abstentions")),
                _fmt(row.get("answerable")),
                _fmt(row.get("correct")),
                _fmt(row.get("answered")),
                _fmt(row.get("judge_calls")),
                "pending" if row.get("cost_cny") is None else "%.4f" % row["cost_cny"],
            )
        )

    lines += [
        "",
        "## Judge spend",
        "",
        "| quantity | value |",
        "|---|---|",
        "| judge model | `%s` |" % protocol.get("judge_model", "?"),
        "| finished configurations | %s |" % _fmt(totals.get("finished"), 0),
        "| pending configurations | %s |" % _fmt(totals.get("pending"), 0),
        "| judge calls (answers graded) | %s |" % _fmt(totals.get("judge_calls"), 0),
        "| judge tokens in / out | %s / %s |"
        % (_fmt(totals.get("tokens_in"), 0), _fmt(totals.get("tokens_out"), 0)),
        "| price (USD per Mtok, in / out) | %s / %s |"
        % (protocol.get("price_in"), protocol.get("price_out")),
        "| measured spend | $%s / ¥%s |"
        % (
            "%.4f" % (totals.get("cost_usd") or 0.0),
            "%.4f" % (totals.get("cost_cny") or 0.0),
        ),
        "| cache hits / misses | %s / %s |"
        % (_fmt(totals.get("cache_hits"), 0), _fmt(totals.get("cache_misses"), 0)),
        "",
        "Every response is cached by content hash in `%s`, so a second pass over the same "
        "configurations issues no requests and returns identical verdicts — the spend above is "
        "what the first pass cost, and the cache columns say how much of the work was free."
        % protocol.get("cache_path", "data/cache/llm.correctness.sqlite"),
        "",
        "## Pending",
        "",
    ]
    if pending:
        lines.append(
            "These configurations have no finished run directory under `%s` yet. They are listed "
            "as `pending` and contribute no number — a missing run is not a zero."
            % payload.get("runs_root", "runs")
        )
        lines.append("")
        for row in pending:
            lines.append("- `%s`" % row.get("cell", "?"))
    else:
        lines.append("None: every declared configuration has a finished run.")

    lines += [
        "",
        "## Per-item verdicts",
        "",
        "The machine-readable bundle (`reports/correctness.json`) carries one verdict per "
        "answerable item and configuration — `item_id`, whether the system abstained, whether "
        "the judge said the answer was correct, and the judge's one-sentence reason — so any "
        "row above can be spot-checked against the answer it summarises.",
        "",
    ]

    unparsed = [row for row in finished if (row.get("parse_failures") or 0) > 0]
    if unparsed:
        lines += [
            "**Judge replies that did not parse.** These configurations have answerable items "
            "whose judge reply was not a verdict. They are counted as not correct in both "
            "accuracies and reported here, so a flaky judge cannot quietly lower a rate without "
            "being visible:",
            "",
        ]
        for row in unparsed:
            lines.append(
                "- `%s`: %d of %s answerable items (`%s`)"
                % (
                    row.get("cell", "?"),
                    row.get("parse_failures"),
                    row.get("answerable"),
                    row.get("run_id", ""),
                )
            )
        lines.append("")
    else:
        lines += [
            "No judge reply failed to parse: every answerable item carries a verdict.",
            "",
        ]

    excluded = payload.get("excluded_runs") or []
    lines += [
        "## Run directories not scored",
        "",
    ]
    if excluded:
        lines.append(
            "The run root holds finished runs that are not one of the declared configurations. "
            "They are grouped here by the reason they carry no row, rather than scored against a "
            "Golden QA Set they were not run on:"
        )
        lines.append("")
        grouped: Dict[str, List[str]] = {}
        for run in excluded:
            grouped.setdefault(str(run.get("reason", "")), []).append(str(run.get("run_id", "?")))
        for reason in sorted(grouped):
            names = grouped[reason]
            lines.append(
                "- **%d run%s** — %s: %s"
                % (
                    len(names),
                    "" if len(names) == 1 else "s",
                    reason,
                    ", ".join("`%s`" % name for name in names),
                )
            )
    else:
        lines.append("None: every finished run directory under the root is a scored configuration.")
    lines += [
        "",
        "## Regenerate",
        "",
        "```",
        REGENERATE,
        "```",
        "",
        "Run from the checkout that owns the run directories, with `LLM_BASE_URL` and "
        "`LLM_API_KEY` in `.env`. The first pass costs one call per answered item; every later "
        "pass is free and byte-identical because `LLMClient` caches by content hash.",
        "",
    ]
    return "\n".join(lines)


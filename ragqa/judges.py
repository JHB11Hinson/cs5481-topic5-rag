"""Two support judges and their disagreement (ticket 10, ADR-0004).

Containment (`verify.py`) answers one narrow question: does the quoted text
actually occur in the chunk the claim cites? It cannot answer the next one — does
that quoted text *support* the claim? — because two strings can co-occur while the
claim says something the text does not.

So a claim that survives containment is judged twice:

- a local NLI cross-encoder, free and deterministic, which reads (premise =
  chunk text, hypothesis = claim) and returns entailment / neutral / contradiction;
- a hosted model, asked the same question in words and told to give one line of
  reason, which is what a reader would actually do.

Neither is ground truth. `notes/judge-calibration.md` reports Cohen's kappa for
each against 30 hand-labelled claims, and only a judge that clears the stated bar
is allowed to gate the headline numbers. The two verdicts are stored side by side
per claim so the confusion between them is inspectable rather than assumed.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List, Optional, Sequence

JUDGE_SYSTEM = (
    "You are a strict citation checker for a documentation question-answering "
    "system. You are given a CLAIM and the exact text of the source chunk the "
    "claim cites. Decide whether the chunk text supports the claim: the claim must "
    "be entailed by the text, not merely related to it. If the text is about the "
    "right topic but the claim adds or changes a value, a default, a version, or a "
    "condition that the text does not state, the answer is false. Reply with JSON "
    'only: {"supported": true|false, "reason": "<one short sentence>"}'
)

DEFAULT_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"


class NLIJudge:
    """Local cross-encoder entailment; label order is the model's own."""

    provider = "nli"

    def __init__(self, model_id: str = DEFAULT_NLI_MODEL, threshold: float = 0.5,
                 device: str = "cpu", model=None):
        if model is None:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(model_id, max_length=512, device=device)

        self.model_id = model_id
        self.threshold = float(threshold)
        self.model = model
        # Label order belongs to the checkpoint. This one is
        # [entailment, neutral, contradiction] — the reverse of the original MNLI
        # convention — so reading index 2 as "entailment" inverts every verdict.
        self.labels = self._label_order()
        self.entailment_index = (
            self.labels.index("entailment") if "entailment" in self.labels else len(self.labels) - 1
        )
        self.last_stats: Dict[str, Any] = {"calls": 0, "entailed": 0, "labels": self.labels}

    def _label_order(self) -> List[str]:
        config = getattr(getattr(self.model, "model", None), "config", None)
        mapping = getattr(config, "id2label", None) or {}
        if not mapping:
            return ["contradiction", "neutral", "entailment"]  # documented MNLI order
        labels: List[str] = []
        for index in sorted(mapping):
            name = str(mapping[index]).lower()
            if "contradict" in name:
                labels.append("contradiction")
            elif "entail" in name:
                labels.append("entailment")
            else:
                labels.append("neutral")
        return labels

    def judge(self, premise: str, hypothesis: str) -> Dict[str, Any]:
        scores = self.model.predict([(premise[:4000], hypothesis[:1000])])[0]
        # The cross-encoder returns raw logits; they are turned into probabilities
        # here and read through the checkpoint's own label order.
        import numpy as np

        values = np.asarray(scores, dtype=float).reshape(-1)
        if values.size > 1 and values.size == len(self.labels):
            logits = values
            probabilities = np.exp(logits - logits.max())
            probabilities = probabilities / probabilities.sum()
            entailment = float(probabilities[self.entailment_index])
            label = self.labels[int(probabilities.argmax())]
        else:  # a scalar "similarity" head: treat the score itself as confidence
            entailment = float(values[0])
            label = "entailment" if entailment >= self.threshold else "neutral"
        self.last_stats["calls"] += 1
        supported = entailment >= self.threshold and label != "contradiction"
        if supported:
            self.last_stats["entailed"] += 1
        return {
            "label": label,
            "entailment": round(entailment, 4),
            "supported": bool(supported),
        }


class LLMJudge:
    provider = "llm"

    def __init__(self, client, model: str, max_chars: int = 2000, max_tokens: int = 700,
                 reasoning_effort: str = ""):
        if not model:
            raise ValueError("LLMJudge needs a model id")
        self.client = client
        self.model_id = model
        self.max_chars = int(max_chars)
        # `deepseek-v4-pro` answers through a thinking channel, so a 200-token
        # budget can be spent entirely on reasoning and return empty content —
        # which the parser would score as "unsupported" and quietly bias the
        # judge toward false. 700 leaves room for both channels (measured: ~50-80
        # reasoning tokens plus a 25-token answer on the calibration set).
        self.max_tokens = int(max_tokens)
        # `reasoning_effort="none"` skips that channel entirely and is ~10x
        # cheaper; it is opt-in because the judge is meant to deliberate.
        self.reasoning_effort = reasoning_effort
        self.last_stats: Dict[str, Any] = {
            "calls": 0,
            "supported": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "parse_failures": 0,
        }

    def judge(self, claim_text: str, evidence_text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"CLAIM:\n{claim_text[:1000]}\n\n"
                    f"SOURCE CHUNK:\n{evidence_text[: self.max_chars]}"
                ),
            },
        ]
        result = self.client.complete(self.model_id, messages, max_tokens=self.max_tokens,
                                      **_effort_kwargs(self.client, self.reasoning_effort))
        self.last_stats["calls"] += 1
        self.last_stats["tokens_in"] += int(result.get("tokens_in", 0) or 0)
        self.last_stats["tokens_out"] += int(result.get("tokens_out", 0) or 0)
        usage = {
            "tokens_in": int(result.get("tokens_in", 0) or 0),
            "tokens_out": int(result.get("tokens_out", 0) or 0),
        }
        payload = _parse(result.get("text", ""))
        if payload is None or "supported" not in payload:
            self.last_stats["parse_failures"] += 1
            return {"supported": False, "reason": "judge reply was not parseable", **usage}
        supported = bool(payload.get("supported"))
        if supported:
            self.last_stats["supported"] += 1
        return {"supported": supported, "reason": str(payload.get("reason", ""))[:300], **usage}


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _effort_kwargs(client, effort: str) -> Dict[str, Any]:
    """Pass `reasoning_effort` only to a client that declares it.

    `LLMClient` gained the knob after the judge was written, and a client that
    does not accept it (a test double, an older checkout) must keep working, so
    the capability is detected rather than assumed.
    """
    if not effort:
        return {}
    try:
        parameters = inspect.signature(client.complete).parameters
    except (TypeError, ValueError):
        return {}
    return {"reasoning_effort": effort} if "reasoning_effort" in parameters else {}


class SupportJudges:
    """The second verification layer, applied to claims that survived containment."""

    def __init__(self, nli: Optional[NLIJudge] = None, llm: Optional[LLMJudge] = None):
        self.nli = nli
        self.llm = llm

    @property
    def enabled(self) -> bool:
        return self.nli is not None or self.llm is not None

    def judge_claim(self, claim: Dict[str, Any], verdict: Dict[str, Any],
                    retrieved: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Annotate one containment verdict in place and return it."""
        if not verdict.get("supported"):
            # Containment failed: there is no verified span to judge support for, so
            # asking a model what it thinks of an unlocatable quote would only add noise.
            verdict["nli_supported"] = None
            verdict["judge_supported"] = None
            return verdict
        text = next(
            (hit["text"] for hit in retrieved if hit["chunk_id"] == claim["chunk_id"]), ""
        )
        claim_text = str(claim.get("text") or claim.get("quote") or "")
        if self.nli is not None:
            outcome = self.nli.judge(text, claim_text)
            verdict["nli_label"] = outcome["label"]
            verdict["nli_score"] = outcome["entailment"]
            verdict["nli_supported"] = outcome["supported"]
        if self.llm is not None:
            outcome = self.llm.judge(claim_text, text)
            verdict["judge_supported"] = outcome["supported"]
            verdict["judge_reason"] = outcome["reason"]
            # Per-claim usage, so a calibration or a run can price exactly the
            # claims it judged instead of only the aggregate (ticket 10).
            verdict["judge_tokens_in"] = int(outcome.get("tokens_in", 0) or 0)
            verdict["judge_tokens_out"] = int(outcome.get("tokens_out", 0) or 0)
        layers = [
            verdict.get("nli_supported"),
            verdict.get("judge_supported"),
        ]
        verdict["supported"] = bool(verdict["supported"]) and all(
            layer is not False for layer in layers
        )
        if not verdict["supported"]:
            verdict["error_class"] = verdict.get("error_class") or "unsupported_by_judge"
            verdict["detail"] = (
                verdict.get("detail")
                or "; ".join(
                    filter(
                        None,
                        [
                            ""
                            if verdict.get("nli_supported") in (None, True)
                            else f"nli={verdict.get('nli_label')}",
                            ""
                            if verdict.get("judge_supported") in (None, True)
                            else f"judge={verdict.get('judge_reason', 'no')}",
                        ],
                    )
                )
            )
        return verdict

    def stats(self) -> Dict[str, Any]:
        return {
            "nli": dict(self.nli.last_stats) if self.nli is not None else None,
            "llm": dict(self.llm.last_stats) if self.llm is not None else None,
        }

    def close(self) -> None:
        for judge in (self.nli, self.llm):
            closer = getattr(judge, "close", None)
            if callable(closer):
                closer()


def make(cfg):
    """Build the judge stack a configuration asked for, or None."""
    if not bool(cfg["judge.enabled"]):
        return None
    nli = NLIJudge(
        model_id=cfg["judge.nli_model"],
        threshold=float(cfg["judge.nli_threshold"]),
    )
    llm = None
    model = cfg["judge.llm_model"] or cfg["llm.model_judge"]
    if model:
        from .llm import LLMClient

        client = LLMClient(
            base_url=cfg["llm.base_url"],
            cache_path=cfg["llm.cache_path"] + ".judge",
            timeout=int(cfg["llm.timeout"]),
            temperature=0.0,
            session_header=cfg["llm.session_header"],
            session_id=cfg["llm.session_id"],
        )
        llm = LLMJudge(client, model=model, max_chars=int(cfg["judge.llm_max_chars"]))
    return SupportJudges(nli=nli, llm=llm)


def confusion(verdicts: List[Dict[str, Any]]) -> Dict[str, int]:
    """NLI × judge agreement grid over claims both layers actually judged."""
    grid = {"both_supported": 0, "neither": 0, "nli_only": 0, "judge_only": 0}
    for verdict in verdicts:
        nli = verdict.get("nli_supported")
        judge = verdict.get("judge_supported")
        if nli is None or judge is None:
            continue
        if nli and judge:
            grid["both_supported"] += 1
        elif not nli and not judge:
            grid["neither"] += 1
        elif nli:
            grid["nli_only"] += 1
        else:
            grid["judge_only"] += 1
    return grid


def kappa(human: Sequence[bool], predicted: Sequence[bool]) -> float:
    """Cohen's kappa for two binary labellings (ticket 10).

    Agreement is corrected for what the two raters would agree on by chance,
    because the interesting claims in a RAG citation set are mostly supported:
    a judge that answers "supported" to everything scores high raw agreement and
    says nothing. Where chance agreement is total — both raters constant — kappa
    is undefined and 0.0 is returned rather than a flattering 1.0.
    """
    left = [bool(value) for value in human]
    right = [bool(value) for value in predicted]
    if len(left) != len(right):
        raise ValueError(
            f"kappa needs one predicted label per human label, got {len(left)} and {len(right)}"
        )
    if not left:
        raise ValueError("kappa needs at least one labelled pair")
    total = float(len(left))
    observed = sum(1 for a, b in zip(left, right) if a == b) / total
    positive_left = sum(left) / total
    positive_right = sum(right) / total
    chance = positive_left * positive_right + (1.0 - positive_left) * (1.0 - positive_right)
    if chance >= 1.0 - 1e-12:
        return 0.0
    return (observed - chance) / (1.0 - chance)


def score_against_human(
    human: Sequence[bool], predicted: Sequence[Optional[bool]]
) -> Dict[str, Any]:
    """One judge layer against the hand labels: agreement, precision, recall, kappa.

    `predicted` may hold None for a claim the layer never judged (containment
    failed, so no model was asked). Those rows are counted as skipped and left
    out of every figure. The positive class is "supported": precision answers
    "of the citations this judge passed, how many were really supported", recall
    answers "of the citations that were really supported, how many did it pass".
    """
    if len(human) != len(predicted):
        raise ValueError(
            f"need one predicted label per human label, got {len(predicted)} and {len(human)}"
        )
    judged = [(bool(h), None if p is None else bool(p)) for h, p in zip(human, predicted)]
    resolved = [(h, p) for h, p in judged if p is not None]
    tp = sum(1 for h, p in resolved if h and p)
    fp = sum(1 for h, p in resolved if not h and p)
    fn = sum(1 for h, p in resolved if h and not p)
    tn = sum(1 for h, p in resolved if not h and not p)
    total = len(resolved)

    def ratio(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    return {
        "n": total,
        "skipped": len(judged) - total,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "agreement": ratio(tp + tn, total),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "kappa": round(kappa([h for h, _ in resolved], [p for _, p in resolved]), 4)
        if total
        else 0.0,
    }


def rerun_verification(run_dir: str, write: bool = True) -> int:
    """`ragqa verify --run runs/<id>`: re-check a finished run against stored chunks.

    Nothing is re-generated, so this is the cheap way to change a judge threshold
    and see what the citation numbers would have been.
    """
    import os

    from .corpus import read_jsonl
    from .verify import check_claims

    predictions = read_jsonl(os.path.join(run_dir, "predictions.jsonl"))
    chunks = {row["chunk_id"]: row for row in read_jsonl(os.path.join(run_dir, "chunks.jsonl"))}
    rows = []
    for prediction in predictions:
        retrieved = []
        for hit in prediction.get("retrieved", []):
            chunk = chunks.get(hit["chunk_id"])
            if chunk is None:
                continue
            retrieved.append({**hit, "text": chunk["text"]})
        verdicts = check_claims(prediction.get("claims", []), retrieved)
        for verdict in verdicts:
            rows.append({"item_id": prediction["item_id"], **verdict})
    print(f"{len(predictions)} predictions, {len(rows)} claims re-verified from {run_dir}")
    if write:
        target = os.path.join(run_dir, "citations.recheck.jsonl")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"wrote {target}")
    supported = sum(1 for row in rows if row["supported"])
    if rows:
        print(f"containment precision {supported / len(rows):.4f}")
    return 0

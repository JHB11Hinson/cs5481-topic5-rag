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

import json
from typing import Any, Dict, List, Optional

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
                 device: str = "cpu"):
        from sentence_transformers import CrossEncoder

        self.model_id = model_id
        self.threshold = float(threshold)
        self.model = CrossEncoder(model_id, max_length=512, device=device)
        self.last_stats: Dict[str, Any] = {"calls": 0, "entailed": 0}

    def judge(self, premise: str, hypothesis: str) -> Dict[str, Any]:
        scores = self.model.predict([(premise[:4000], hypothesis[:1000])])[0]
        # CrossEncoder on an NLI head returns logits in the model's label order; the
        # MNLI convention used here is [contradiction, neutral, entailment].
        import numpy as np

        values = np.asarray(scores, dtype=float).reshape(-1)
        if values.size == 3:
            logits = values
            probabilities = np.exp(logits - logits.max())
            probabilities = probabilities / probabilities.sum()
            entailment = float(probabilities[2])
            label = ["contradiction", "neutral", "entailment"][int(probabilities.argmax())]
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

    def __init__(self, client, model: str, max_chars: int = 2000):
        if not model:
            raise ValueError("LLMJudge needs a model id")
        self.client = client
        self.model_id = model
        self.max_chars = int(max_chars)
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
        result = self.client.complete(self.model_id, messages, max_tokens=200)
        self.last_stats["calls"] += 1
        self.last_stats["tokens_in"] += int(result.get("tokens_in", 0) or 0)
        self.last_stats["tokens_out"] += int(result.get("tokens_out", 0) or 0)
        payload = _parse(result.get("text", ""))
        if payload is None or "supported" not in payload:
            self.last_stats["parse_failures"] += 1
            return {"supported": False, "reason": "judge reply was not parseable"}
        supported = bool(payload.get("supported"))
        if supported:
            self.last_stats["supported"] += 1
        return {"supported": supported, "reason": str(payload.get("reason", ""))[:300]}


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

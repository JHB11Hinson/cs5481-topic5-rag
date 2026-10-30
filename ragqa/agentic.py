"""The bounded agentic loop (ticket 13).

A single retrieval round is the right default and the wrong answer for questions
that never surface their evidence: the query is phrased in a user's vocabulary,
the document is written in the product's. The loop exists to measure whether a
second round, with the question rewritten into the corpus's vocabulary, pays for
itself — in recall, in citation precision, in latency, and in money.

Two rules make it an experiment rather than a gadget:

- **The trigger is a runtime signal, not the answer key.** A round "fails" when no
  chunk clears the configured score threshold. The golden evidence is never
  consulted while running; it is only used afterwards to score the result.
- **The cap is hard.** `retrieval.hops` bounds the number of rounds, and every run
  ends with exactly one recorded stop reason: `hit_first_round`,
  `hit_after_rewrite`, `cap_reached`, or `abstained`.

The rewrite is a cheap-model call returning JSON sub-queries. Round results are
fused with the same RRF the hybrid retriever uses, so a question that is answered
well by two of three sub-queries outranks one that is answered by one.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from .sparse import rrf_fuse

STOP_FIRST_ROUND = "hit_first_round"
STOP_AFTER_REWRITE = "hit_after_rewrite"
STOP_CAP = "cap_reached"
STOP_ABSTAINED = "abstained"

REWRITE_SYSTEM = (
    "You rewrite a documentation search query. You are given the user's question "
    "and the headings of the chunks that scored best, if any. Produce up to three "
    "short search queries that use the vocabulary a technical reference would use "
    "for this topic — setting names, command names, page titles. Do not answer the "
    "question. Reply with JSON only: {\"queries\": [\"...\"]}"
)


def _parse_queries(raw: str) -> List[str]:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    queries = payload.get("queries") if isinstance(payload, dict) else None
    if not isinstance(queries, list):
        return []
    return [str(query).strip() for query in queries if str(query).strip()][:3]


class Rewriter:
    """Cheap-model query rewriting; deterministic through the LLM response cache."""

    def __init__(self, client, model: str):
        if not model:
            raise ValueError("Rewriter needs a model id")
        self.client = client
        self.model_id = model
        self.last_stats = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "parse_failures": 0}

    def rewrite(self, question: str, hints: List[str]) -> List[str]:
        messages = [
            {"role": "system", "content": REWRITE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Best headings so far: {' | '.join(hints[:5]) if hints else '(none)'}"
                ),
            },
        ]
        result = self.client.complete(self.model_id, messages, max_tokens=200)
        self.last_stats["calls"] += 1
        self.last_stats["tokens_in"] += int(result.get("tokens_in", 0) or 0)
        self.last_stats["tokens_out"] += int(result.get("tokens_out", 0) or 0)
        queries = _parse_queries(result.get("text", ""))
        if not queries:
            self.last_stats["parse_failures"] += 1
        return queries

    def close(self) -> None:
        closer = getattr(self.client, "close", None)
        if callable(closer):
            closer()


def _fuse(rounds: List[List[Dict[str, Any]]], k: int, rrf_k: int) -> List[Dict[str, Any]]:
    """Fuse rounds by RRF for ordering, but keep each hit on its own score scale.

    The abstention threshold and the trigger threshold both live on the retrieval
    mode's scale (logits, RRF sums, cosine). Overwriting `score` with the fused
    value would silently move every later decision onto a fourth scale, so the
    fused number is recorded separately and only used to order.
    """
    if len(rounds) == 1:
        return rounds[0]
    branches = {
        f"round{index}": [(hit["chunk_id"], float(hit["score"])) for hit in hits]
        for index, hits in enumerate(rounds)
        if hits
    }
    by_id: Dict[str, Dict[str, Any]] = {}
    best_score: Dict[str, float] = {}
    for hits in rounds:
        for hit in hits:
            by_id.setdefault(hit["chunk_id"], hit)
            best_score[hit["chunk_id"]] = max(
                best_score.get(hit["chunk_id"], float("-inf")), float(hit["score"])
            )
    fused = rrf_fuse(branches, rrf_k=rrf_k, limit=k)
    out: List[Dict[str, Any]] = []
    for rank, (chunk_id, score, ranks) in enumerate(fused, start=1):
        hit = dict(by_id[chunk_id])
        hit["fusion_score"] = float(score)
        hit["score"] = best_score[chunk_id]
        hit["branches"] = ranks
        hit["rank"] = rank
        out.append(hit)
    return out


def retrieve_with_hops(
    retrieve_for_query: Callable[[str], List[Dict[str, Any]]],
    question: str,
    k: int,
    threshold: float,
    max_hops: int = 1,
    rewriter: Optional[Rewriter] = None,
    rrf_k: int = 60,
    headings: Callable[[List[Dict[str, Any]]], List[str]] = lambda hits: [
        hit.get("heading_path", "") for hit in hits if hit.get("heading_path")
    ],
) -> tuple:
    """Run up to `max_hops` rounds; return (hits, meta).

    `retrieve_for_query` embeds one query string and returns ranked hits, so the
    first round and every rewritten round go through exactly the same retrieval
    code — otherwise the hop curve would measure two different systems.
    """
    meta: Dict[str, Any] = {
        "hops": 0,
        "queries": [question],
        "stop_reason": STOP_ABSTAINED,
        "scores": [],
    }
    first = retrieve_for_query(question)
    meta["hops"] = 1
    meta["scores"].append(round(first[0]["score"], 6) if first else 0.0)
    if first and first[0]["score"] >= threshold:
        meta["stop_reason"] = STOP_FIRST_ROUND
        return first, meta

    if max_hops <= 1 or rewriter is None:
        meta["stop_reason"] = STOP_CAP if first else STOP_ABSTAINED
        return first, meta

    rounds: List[List[Dict[str, Any]]] = [first]
    while meta["hops"] < max_hops:
        queries = rewriter.rewrite(question, headings(rounds[-1]))
        if not queries:
            break
        meta["queries"].extend(queries)
        round_hits = [retrieve_for_query(query) for query in queries]
        merged = _fuse(round_hits + rounds, k=k, rrf_k=rrf_k)
        rounds.append(merged)
        meta["hops"] += 1
        best = max((hit["score"] for hit in merged), default=0.0)
        meta["scores"].append(round(best, 6))
        if merged and best >= threshold:
            meta["stop_reason"] = STOP_AFTER_REWRITE
            return merged[:k], meta

    final = rounds[-1] if rounds else []
    meta["stop_reason"] = STOP_CAP if final else STOP_ABSTAINED
    return final[:k], meta


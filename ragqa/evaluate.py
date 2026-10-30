"""Metrics.

Retrieval hits are decided by locating the golden evidence quote inside returned
chunk text after whitespace normalisation — never by comparing chunk ids, which
change with every chunk strategy (golden/SPEC.md).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from .textutil import normalize, overlap_ratio


def _first_hit_rank(retrieved: Sequence[Dict[str, Any]], quotes: Sequence[str]) -> int:
    normalized = [normalize(q) for q in quotes if q]
    for hit in retrieved:
        text = normalize(hit["text"])
        for quote in normalized:
            if quote and quote in text:
                return int(hit["rank"])
    return 0


def _percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round(fraction * (len(ordered) - 1)))
    return float(ordered[index])


def grounding_metrics(verdicts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-layer precision over every claim, so the layers can be compared.

    Containment is arithmetic and cannot be wrong about what it measures; the NLI
    and model layers are opinions, which is why their pass rates are reported
    separately and never silently folded into one "citation precision".

    A layer that judged nothing has no precision, and the ratio says so: `None`
    rather than `0.0`. Zero is a measurement ("every claim this layer saw was
    rejected"); a run whose judge was never called has made no such measurement,
    and publishing 0.0 for it puts a fake failure into the table.
    """
    claims = len(verdicts)
    # `containment_ok` only: falling back to `supported` re-folded the judge layer
    # into the arithmetic one, so a claim the model rejected looked like a
    # containment failure.
    containment = [v for v in verdicts if v.get("containment_ok")]
    nli = [v for v in verdicts if v.get("nli_supported") is not None]
    judge = [v for v in verdicts if v.get("judge_supported") is not None]
    resolved = [v for v in verdicts if v.get("span_start") is not None]

    def ratio(part: int, whole: int) -> Optional[float]:
        return round(part / whole, 4) if whole else None

    return {
        "claims": claims,
        "containment_pass": len(containment),
        "containment_precision": ratio(len(containment), claims),
        "nli_judged": len(nli),
        "nli_pass": sum(1 for v in nli if v.get("nli_supported")),
        "nli_precision": ratio(sum(1 for v in nli if v.get("nli_supported")), len(nli)),
        "judge_judged": len(judge),
        "judge_pass": sum(1 for v in judge if v.get("judge_supported")),
        "judge_precision": ratio(sum(1 for v in judge if v.get("judge_supported")), len(judge)),
        "span_resolved": len(resolved),
        "span_resolved_rate": ratio(len(resolved), claims),
    }


def compute(
    items: List[Dict[str, Any]],
    per_item: List[Dict[str, Any]],
    k: int,
) -> Dict[str, Any]:
    answerable = [p for p in per_item if p["answerable"]]
    unanswerable = [p for p in per_item if not p["answerable"]]

    ranks = []
    ndcg_terms = []
    for entry in answerable:
        rank = _first_hit_rank(entry["retrieved"], entry["quotes"])
        ranks.append(rank)
        ndcg_terms.append(1.0 / math.log2(rank + 1) if rank else 0.0)

    hit_rate = sum(1 for r in ranks if r) / float(len(ranks)) if ranks else 0.0
    mrr = sum(1.0 / r for r in ranks if r) / float(len(ranks)) if ranks else 0.0
    ndcg = sum(ndcg_terms) / float(len(ndcg_terms)) if ndcg_terms else 0.0

    claims = [c for entry in per_item for c in entry["verdicts"]]
    valid = [c for c in claims if c["supported"]]
    failure_classes: Dict[str, int] = {}
    for claim in claims:
        if not claim["supported"]:
            failure_classes[claim["error_class"]] = failure_classes.get(claim["error_class"], 0) + 1

    cited_items = sum(
        1
        for entry in answerable
        if any(c["supported"] for c in entry["verdicts"]) and not entry["abstained"]
    )
    # Span hit rate is counted from verified spans, not from the generator's own
    # claim about what it quoted: a claim only counts when the verifier located the
    # quote inside the cited chunk (ticket 10).
    span_hits = sum(1 for claim in claims if claim.get("span_start") is not None)

    abstained_negatives = sum(1 for e in unanswerable if e["abstained"])
    over_abstain = sum(1 for e in answerable if e["abstained"])

    return {
        "items": {
            "total": len(per_item),
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
        },
        "retrieval": {
            "k": k,
            "hit_rate": round(hit_rate, 4),
            "recall_at_k": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            "ndcg_at_10": round(ndcg, 4),
            "misses": [e["item_id"] for e, r in zip(answerable, ranks) if not r],
        },
        "citations": {
            "claims": len(claims),
            "supported": len(valid),
            "citation_precision": round(len(valid) / len(claims), 4) if claims else 0.0,
            "citation_recall": round(cited_items / len(answerable), 4) if answerable else 0.0,
            "span_hit_rate": round(span_hits / len(claims), 4) if claims else 0.0,
            "containment_failures": failure_classes,
        },
        "abstention": {
            "abstained_answerable": over_abstain,
            "over_abstain_rate": round(over_abstain / len(answerable), 4) if answerable else 0.0,
            "abstained_unanswerable": abstained_negatives,
            "abstention_recall_on_negatives": round(
                abstained_negatives / len(unanswerable), 4
            )
            if unanswerable
            else 0.0,
            "under_abstain": len(unanswerable) - abstained_negatives,
        },
        "system": {
            "effective_rate": 1.0,
            "cost_cny": 0.0,
        },
    }

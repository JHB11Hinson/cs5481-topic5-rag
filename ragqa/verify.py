"""Citation verification, layer one: containment.

A claim is only checkable if the chunk it cites was actually retrieved and the
text it quotes really occurs in that chunk (ADR-0004). That is arithmetic, not
judgement, so it runs before any model is asked for an opinion.

Models return a verbatim `quote`, not character offsets — a model cannot count
characters, and a wrong offset would make a true citation look false. The span is
therefore derived here by string search, and a quote that does not occur is its
own failure class.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .textutil import locate_normalized, normalize


def check_claims(
    claims: List[Dict[str, Any]], retrieved: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    context = {hit["chunk_id"]: hit for hit in retrieved}
    verdicts: List[Dict[str, Any]] = []

    for claim in claims:
        chunk_id = claim["chunk_id"]
        error_class = ""
        detail = ""
        span = (-1, -1)

        if chunk_id not in context:
            error_class = "chunk_not_retrieved"
            detail = "cited chunk was not in the context handed to the generator"
        else:
            text = context[chunk_id]["text"]
            quote = str(claim.get("quote") or "").strip()
            if quote:
                span = locate_normalized(text, quote)
                if span[0] < 0:
                    error_class = "quote_not_in_chunk"
                    detail = "quoted text does not occur in the cited chunk"
                else:
                    claim.setdefault("span_start", span[0])
                    claim.setdefault("span_end", span[1])
                    claim.setdefault("text", normalize(text[span[0]:span[1]]))
            else:
                start = int(claim.get("span_start", -1))
                end = int(claim.get("span_end", -1))
                if not (0 <= start < end <= len(text)):
                    error_class = "span_out_of_bounds"
                    detail = f"span [{start}, {end}) outside chunk of {len(text)} chars"
                elif normalize(text[start:end]) != normalize(str(claim.get("text", ""))):
                    error_class = "span_text_mismatch"
                    detail = "cited span does not contain the claim text"
                else:
                    span = (start, end)

        verdicts.append(
            {
                "claim_id": claim.get("claim_id", ""),
                "chunk_id": chunk_id,
                "supported": error_class == "",
                "error_class": error_class,
                "detail": detail,
                "span_start": span[0] if span[0] >= 0 else None,
                "span_end": span[1] if span[0] >= 0 else None,
            }
        )
    return verdicts

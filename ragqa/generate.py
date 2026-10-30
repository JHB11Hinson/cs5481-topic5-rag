"""Answer generation.

Two generators share one output contract: claims that name a retrieved chunk and
carry the exact text they rest on.

`StubGenerator` picks the sentence or line of the top chunk with the most
vocabulary overlap with the question. It is a pipeline probe, not a reader.

`LLMGenerator` (ticket 06) asks a hosted model to answer only from the supplied
chunks and to return JSON. It is told to copy a verbatim `quote` per claim rather
than to produce character offsets: a model cannot count characters, but string
search can, so the offsets are derived in `verify.py` instead of trusted here.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from .textutil import normalize, overlap_ratio, sentence_spans, token_set

SYSTEM_PROMPT = (
    "You answer questions about a product's documentation using ONLY the numbered "
    "context chunks provided. Each claim you make must be supported by a chunk and "
    "must carry a `quote` copied verbatim from that chunk's text, with its line "
    "breaks normalised but its wording unchanged. Never use outside knowledge. "
    "If the context does not contain the answer, set answerable to false and return "
    "no claims. Reply with JSON only."
)

OUTPUT_SCHEMA = (
    '{"answerable": true|false, '
    '"claims": [{"text": "<claim>", "chunk_id": "<id>", "quote": "<verbatim text>"}], '
    '"abstain_reason": "<why, when answerable is false>"}'
)


def _content_tokens(question: str) -> set:
    """Long, specific tokens the answer has to mention to be about the question."""
    return {token for token in token_set(question) if len(token) >= 8}


def _candidates(text: str) -> List[Tuple[str, int, int]]:
    """Sentences, plus non-empty lines that carry no terminal punctuation."""
    found = list(sentence_spans(text))
    seen = {(start, end) for _, start, end in found}
    offset = 0
    for raw in text.splitlines(True):
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        if stripped:
            lead = len(line) - len(line.lstrip())
            start = offset + lead
            end = start + len(stripped)
            if (start, end) not in seen:
                found.append((stripped, start, end))
                seen.add((start, end))
        offset += len(raw)
    return found


class StubGenerator:
    provider = "stub"
    model_id = "stub-generator"
    last_stats: Dict[str, int] = {"hits": 0, "misses": 0}

    def generate(
        self,
        item: Dict[str, Any],
        retrieved: List[Dict[str, Any]],
        threshold: float,
        max_claims: int,
        min_claim_overlap: float = 0.12,
    ) -> Dict[str, Any]:
        question = item["question"]
        if not retrieved:
            return self._abstain(item, "no_candidates")

        top = retrieved[0]
        if top["score"] < threshold:
            return self._abstain(item, "below_score_threshold")

        claims: List[Dict[str, Any]] = []
        content = _content_tokens(question)
        for hit in retrieved[: max(1, max_claims)]:
            if hit["score"] < threshold:
                continue
            candidates = _candidates(hit["text"])
            if not candidates:
                continue
            best = max(candidates, key=lambda c: overlap_ratio(question, c[0]))
            if overlap_ratio(question, best[0]) < min_claim_overlap:
                continue
            if content and not (content & token_set(best[0])):
                continue
            claims.append(
                {
                    "claim_id": f"{item['id']}-c{len(claims) + 1}",
                    "text": best[0],
                    "chunk_id": hit["chunk_id"],
                    "doc_id": hit["doc_id"],
                    "span_start": best[1],
                    "span_end": best[2],
                }
            )

        if not claims:
            return self._abstain(item, "no_claim_could_be_grounded")
        return self._answer(claims)

    def _answer(self, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "answer_text": " ".join(claim["text"] for claim in claims),
            "claims": claims,
            "citations": [
                {"chunk_id": claim["chunk_id"], "doc_id": claim["doc_id"]} for claim in claims
            ],
            "abstained": False,
            "abstain_reason": "",
            "raw_response": "",
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def _abstain(self, item: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "answer_text": "The documentation provided does not contain an answer to this question.",
            "claims": [],
            "citations": [],
            "abstained": True,
            "abstain_reason": reason,
            "raw_response": "",
            "tokens_in": 0,
            "tokens_out": 0,
        }


class LLMGenerator:
    provider = "llm"

    def __init__(self, client, model: str, context_chunks: int = 8, max_tokens: int = 900):
        self.client = client
        self.model_id = model
        self.context_chunks = int(context_chunks)
        self.max_tokens = int(max_tokens)
        self.last_stats: Dict[str, int] = {"hits": 0, "misses": 0}

    def _messages(self, item: Dict[str, Any], retrieved: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        blocks = []
        for hit in retrieved[: self.context_chunks]:
            blocks.append(
                f"[{hit['chunk_id']}] doc={hit['doc_id']} rank={hit['rank']}\n{hit['text']}"
            )
        context = "\n\n".join(blocks) if blocks else "(no context retrieved)"
        user = (
            f"Question: {item['question']}\n\n"
            f"Context chunks:\n{context}\n\n"
            f"Answer with JSON matching exactly this shape:\n{OUTPUT_SCHEMA}"
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def generate(
        self,
        item: Dict[str, Any],
        retrieved: List[Dict[str, Any]],
        threshold: float,
        max_claims: int,
        min_claim_overlap: float = 0.12,
    ) -> Dict[str, Any]:
        messages = self._messages(item, retrieved)
        result = self.client.complete(self.model_id, messages, max_tokens=self.max_tokens)
        raw = result["text"]
        payload = self._parse(raw)

        if payload is None:
            # One corrective retry, as the ticket allows: the usual cause is a model
            # thinking out loud before the JSON, not a model that cannot answer.
            repair = messages + [
                {"role": "assistant", "content": raw[:2000]},
                {
                    "role": "user",
                    "content": "That was not valid JSON. Reply again with JSON only, "
                    "matching exactly: " + OUTPUT_SCHEMA,
                },
            ]
            retry = self.client.complete(self.model_id, repair, max_tokens=self.max_tokens)
            payload = self._parse(retry["text"])
            result = {
                "text": retry["text"],
                "tokens_in": result.get("tokens_in", 0) + retry.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0) + retry.get("tokens_out", 0),
            }
            raw = retry["text"]

        self.last_stats = dict(getattr(self.client, "last_stats", self.last_stats))
        if payload is None:
            return {
                "answer_text": "",
                "claims": [],
                "citations": [],
                "abstained": False,
                "abstain_reason": "parse_failure",
                "raw_response": raw,
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
                "parse_failure": True,
            }

        claims: List[Dict[str, Any]] = []
        for entry in (payload.get("claims") or [])[: max(1, max_claims)]:
            quote = str(entry.get("quote") or "").strip()
            chunk_id = str(entry.get("chunk_id") or "").strip()
            if not quote or not chunk_id:
                continue
            claims.append(
                {
                    "claim_id": f"{item['id']}-c{len(claims) + 1}",
                    "text": str(entry.get("text") or quote).strip(),
                    "quote": quote,
                    "chunk_id": chunk_id,
                    "doc_id": next(
                        (hit["doc_id"] for hit in retrieved if hit["chunk_id"] == chunk_id), ""
                    ),
                }
            )

        answerable = bool(payload.get("answerable", bool(claims)))
        if not answerable or not claims:
            return {
                "answer_text": str(payload.get("abstain_reason") or
                                   "The documentation provided does not contain an answer."),
                "claims": [],
                "citations": [],
                "abstained": True,
                "abstain_reason": str(payload.get("abstain_reason") or "model_declined"),
                "raw_response": raw,
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
            }

        return {
            "answer_text": normalize(" ".join(claim["text"] for claim in claims)),
            "claims": claims,
            "citations": [
                {"chunk_id": claim["chunk_id"], "doc_id": claim["doc_id"]} for claim in claims
            ],
            "abstained": False,
            "abstain_reason": "",
            "raw_response": raw,
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
        }

    @staticmethod
    def _parse(raw: str):
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text)
            text = re.sub(r"```\s*$", "", text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None


def make(cfg):
    provider = cfg["generate.provider"]
    if provider == "stub":
        return StubGenerator()
    if provider == "llm":
        from .llm import LLMClient

        client = LLMClient(
            base_url=cfg["llm.base_url"],
            api_key="",
            cache_path=cfg["llm.cache_path"],
            timeout=int(cfg["llm.timeout"]),
            temperature=float(cfg["llm.temperature"]),
            session_header=cfg["llm.session_header"],
            session_id=cfg["llm.session_id"],
        )
        return LLMGenerator(
            client,
            model=cfg["llm.model_generate"],
            context_chunks=int(cfg["llm.context_chunks"]),
            max_tokens=int(cfg["llm.max_tokens"]),
        )
    raise ValueError(f"unknown generate.provider {provider!r}")

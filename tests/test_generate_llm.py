from __future__ import annotations

import json

from ragqa import generate, verify
from ragqa.textutil import locate_normalized

CHUNK = {
    "chunk_id": "c1",
    "doc_id": "docs/seal",
    "text": "When you start a Vault server, it starts in a sealed state.\n\n"
            "Unsealing obtains the plaintext root key.",
}
RETRIEVED = [{"chunk_id": "c1", "doc_id": "docs/seal", "rank": 1, "score": 1.0,
              "text": CHUNK["text"]}]


class FakeClient:
    """Stands in for LLMClient: returns a canned JSON body, records the request."""

    def __init__(self, payload, tokens=(100, 20)):
        self.payload = payload
        self.calls = []
        self.last_stats = {"hits": 0, "misses": 1}
        self._tokens = tokens

    def complete(self, model, messages, max_tokens=800, json_mode=True):
        self.calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        return {
            "text": self.payload if isinstance(self.payload, str) else json.dumps(self.payload),
            "tokens_in": self._tokens[0],
            "tokens_out": self._tokens[1],
            "latency_ms": 12.0,
            "cached": False,
        }


ITEM = {"id": "A001", "question": "What state does a Vault server start in?"}


def test_locate_normalized_tolerates_whitespace_and_newlines():
    quote = "it starts in a sealed state.\n\nUnsealing"
    start, end = locate_normalized(CHUNK["text"], quote)
    assert start > 0 and end > start
    assert CHUNK["text"][start:end].startswith("it starts")
    assert locate_normalized(CHUNK["text"], "not present anywhere") == (-1, -1)


def test_llm_generator_parses_claims_and_derives_spans():
    client = FakeClient(
        {
            "answerable": True,
            "claims": [
                {
                    "text": "A Vault server starts sealed.",
                    "chunk_id": "c1",
                    "quote": "it starts in a sealed state",
                }
            ],
            "abstain_reason": "",
        }
    )
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["abstained"] is False
    assert len(answer["claims"]) == 1
    verdicts = verify.check_claims(answer["claims"], RETRIEVED)
    assert verdicts[0]["supported"] is True
    assert verdicts[0]["span_start"] is not None
    assert client.calls[0]["messages"][0]["role"] == "system"
    assert "c1" in client.calls[0]["messages"][1]["content"]


def test_llm_generator_abstains_when_model_declines():
    client = FakeClient({"answerable": False, "claims": [], "abstain_reason": "not in context"})
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["abstained"] is True
    assert answer["abstain_reason"] == "not in context"


def test_fabricated_quote_is_its_own_failure_class():
    client = FakeClient(
        {
            "answerable": True,
            "claims": [
                {"text": "invented", "chunk_id": "c1", "quote": "this sentence is not in the chunk"}
            ],
        }
    )
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    verdicts = verify.check_claims(answer["claims"], RETRIEVED)
    assert verdicts[0]["supported"] is False
    assert verdicts[0]["error_class"] == "quote_not_in_chunk"


def test_malformed_json_is_a_parse_failure_not_a_crash():
    client = FakeClient("I cannot answer that in JSON.")
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["parse_failure"] is True
    assert answer["abstain_reason"] == "parse_failure"


def test_fenced_json_is_accepted():
    payload = '```json\n{"answerable": true, "claims": [{"text": "t", "chunk_id": "c1", "quote": "sealed state"}]}\n```'
    client = FakeClient(payload)
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["abstained"] is False
    assert verify.check_claims(answer["claims"], RETRIEVED)[0]["supported"] is True


def test_claim_citing_an_unretrieved_chunk_is_rejected():
    claims = [{"claim_id": "x", "text": "t", "chunk_id": "c9", "quote": "anything"}]
    verdicts = verify.check_claims(claims, RETRIEVED)
    assert verdicts[0]["error_class"] == "chunk_not_retrieved"

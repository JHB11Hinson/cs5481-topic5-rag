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
    """Stands in for LLMClient: returns a canned JSON body, records the request.

    `payload` may be a list, which is how a two-call path (grounded, then ungrounded)
    is exercised: call *n* gets entry *n*, and the last entry repeats.
    """

    def __init__(self, payload, tokens=(100, 20)):
        self.payload = payload
        self.calls = []
        self.last_stats = {"hits": 0, "misses": 1}
        self._tokens = tokens

    def _body(self):
        if isinstance(self.payload, list):
            index = min(len(self.calls) - 1, len(self.payload) - 1)
            return self.payload[index]
        return self.payload

    def complete(self, model, messages, max_tokens=800, json_mode=True):
        self.calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        body = self._body()
        return {
            "text": body if isinstance(body, str) else json.dumps(body),
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


# ---- the gap policy (ADR-0020) ------------------------------------------------

DECLINE = {"answerable": False, "claims": [], "abstain_reason": "not in context"}
GENERAL = {
    "known": True,
    "answer": "Auto-unseal wraps the master key with a KMS key so operators need not "
              "hold a shard by hand.",
    "caveat": "Confirm the wrap/unwrap API is available in the release you run.",
}


def test_a_declined_question_is_answered_in_general_terms_when_the_policy_is_on():
    client = FakeClient([DECLINE, GENERAL])
    generator = generate.LLMGenerator(client, model="test-model", ungrounded=True)
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert len(client.calls) == 2, "one grounded call, then one ungrounded call"
    assert answer["answer_mode"] == "ungrounded_general"
    # The label is ours, fixed, and comes first; the model's paragraph follows it.
    assert answer["answer_text"].startswith(generate.GAP_NOTE)
    assert GENERAL["answer"] in answer["answer_text"]
    # Nothing about it may look like a citation.
    assert answer["claims"] == [] and answer["citations"] == []
    # The knowledge base still did not answer, so every existing metric keeps counting
    # this item as an abstention rather than as a grounded answer.
    assert answer["abstained"] is True
    assert answer["abstain_reason"] == "not in context"
    assert answer["caveat"].startswith("Confirm")


def test_the_ungrounded_call_is_told_not_to_invent_citations():
    client = FakeClient([DECLINE, GENERAL])
    generator = generate.LLMGenerator(client, model="test-model", ungrounded=True)
    generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    system = client.calls[1]["messages"][0]["content"]
    assert "Do not invent citations" in system
    assert "Never use outside knowledge" not in system


def test_the_policy_is_off_by_default_and_costs_one_call():
    client = FakeClient([DECLINE, GENERAL])
    generator = generate.LLMGenerator(client, model="test-model")
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert len(client.calls) == 1
    assert answer["answer_mode"] == "abstained"
    assert answer["general_answer"] == ""


def test_a_grounded_answer_never_pays_for_the_second_call():
    client = FakeClient([{"answerable": True, "claims": [
        {"text": "A Vault server starts sealed.", "chunk_id": "c1",
         "quote": "it starts in a sealed state"}]}, GENERAL])
    generator = generate.LLMGenerator(client, model="test-model", ungrounded=True)
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert len(client.calls) == 1
    assert answer["answer_mode"] == "grounded"


def test_a_broken_second_call_leaves_the_honest_abstention_standing():
    client = FakeClient([DECLINE, "Sure! Here is a general answer in prose."])
    generator = generate.LLMGenerator(client, model="test-model", ungrounded=True)
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["abstained"] is True
    assert answer["answer_mode"] == "abstained"
    assert answer["general_answer"] == ""
    # Tokens from both calls are still accounted, because both were paid for.
    assert answer["tokens_in"] == 200


def test_a_parse_failure_is_not_a_knowledge_gap():
    # Both the first attempt and its one corrective retry come back unparsable.
    client = FakeClient(["not json at all", "still not json", GENERAL])
    generator = generate.LLMGenerator(client, model="test-model", ungrounded=True)
    answer = generator.generate(ITEM, RETRIEVED, threshold=0.0, max_claims=2)
    assert answer["answer_mode"] == "parse_failure"
    assert answer["general_answer"] == ""

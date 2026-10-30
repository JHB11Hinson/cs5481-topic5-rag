from __future__ import annotations

from ragqa import judges, verify


def _retrieved(text="the answer is 16 threads"):
    return [{"chunk_id": "c1", "doc_id": "d", "rank": 1, "score": 0.9, "text": text}]


def _claim(text="the answer is 16 threads"):
    return {
        "claim_id": "c1",
        "text": text,
        "quote": text,
        "chunk_id": "c1",
        "doc_id": "d",
    }


class FakeNLI:
    def __init__(self, supported, label="entailment", score=0.9):
        self.supported = supported
        self.label = label
        self.score = score
        self.calls = 0

    def judge(self, premise, hypothesis):
        self.calls += 1
        return {"label": self.label, "entailment": self.score, "supported": self.supported}


class FakeLLMJudge:
    def __init__(self, supported, reason="ok"):
        self.supported = supported
        self.reason = reason
        self.calls = 0

    def judge(self, claim_text, evidence_text):
        self.calls += 1
        return {"supported": self.supported, "reason": self.reason}


def test_a_claim_that_survives_containment_is_judged_twice():
    claim = _claim()
    verdicts = verify.check_claims([claim], _retrieved())
    stack = judges.SupportJudges(nli=FakeNLI(True), llm=FakeLLMJudge(True))
    stack.judge_claim(claim, verdicts[0], _retrieved())
    assert verdicts[0]["supported"] is True
    assert verdicts[0]["nli_supported"] is True
    assert verdicts[0]["judge_supported"] is True


def test_a_judge_can_veto_a_contained_citation():
    claim = _claim("the answer is 32 threads")
    retrieved = _retrieved("the answer is 16 threads")
    verdicts = verify.check_claims([_claim()], retrieved)  # containment passes
    stack = judges.SupportJudges(nli=FakeNLI(False, "contradiction", 0.1), llm=None)
    stack.judge_claim(_claim(), verdicts[0], retrieved)
    assert verdicts[0]["supported"] is False
    assert verdicts[0]["error_class"] == "unsupported_by_judge"


def test_containment_failure_is_never_sent_to_a_judge():
    claim = _claim("text that is not in the chunk")
    retrieved = _retrieved()
    verdicts = verify.check_claims([claim], retrieved)
    nli = FakeNLI(True)
    stack = judges.SupportJudges(nli=nli, llm=None)
    stack.judge_claim(claim, verdicts[0], retrieved)
    assert verdicts[0]["supported"] is False
    assert nli.calls == 0


def test_confusion_grid_counts_only_claims_both_layers_judged():
    verdicts = [
        {"nli_supported": True, "judge_supported": True},
        {"nli_supported": False, "judge_supported": False},
        {"nli_supported": True, "judge_supported": False},
        {"nli_supported": False, "judge_supported": True},
        {"nli_supported": None, "judge_supported": True},
    ]
    grid = judges.confusion(verdicts)
    assert grid == {
        "both_supported": 1,
        "neither": 1,
        "nli_only": 1,
        "judge_only": 1,
    }


def test_llm_judge_parses_a_fenced_reply_and_records_cost():
    class Client:
        def __init__(self, text, tokens_in=100, tokens_out=20):
            self.text = text
            self.tokens_in = tokens_in
            self.tokens_out = tokens_out

        def complete(self, model, messages, max_tokens=200, json_mode=False):
            return {
                "text": self.text,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
            }

    judge = judges.LLMJudge(Client('```json\n{"supported": false, "reason": "adds a value"}\n```'), "m")
    outcome = judge.judge("claim", "evidence")
    assert outcome["supported"] is False
    assert "adds a value" in outcome["reason"]
    assert judge.last_stats["tokens_in"] == 100

    garbage = judges.LLMJudge(Client("the model rambled"), "m")
    assert garbage.judge("claim", "evidence")["supported"] is False
    assert garbage.last_stats["parse_failures"] == 1

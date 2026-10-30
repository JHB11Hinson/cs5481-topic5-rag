from __future__ import annotations

from ragqa import agentic


def _hit(chunk_id, score):
    return {"chunk_id": chunk_id, "doc_id": "d", "rank": 1, "score": score, "text": "t"}


class FakeRewriter:
    def __init__(self, queries):
        self.queries = queries
        self.calls = 0

    def rewrite(self, question, hints):
        self.calls += 1
        return list(self.queries)


def test_single_hop_stops_when_the_first_round_clears_the_threshold():
    calls = []

    def retrieve_for_query(query):
        calls.append(query)
        return [_hit("c1", 0.9)]

    hits, meta = agentic.retrieve_with_hops(
        retrieve_for_query, "q", k=5, threshold=0.5, max_hops=1
    )
    assert meta["stop_reason"] == agentic.STOP_FIRST_ROUND
    assert meta["hops"] == 1
    assert calls == ["q"]
    assert hits[0]["chunk_id"] == "c1"


def test_rewrite_runs_after_a_failed_round_and_merges_results():
    responses = {  # first round is weak, rewritten rounds are strong
        "q": [_hit("weak", 0.1)],
        "q rewritten": [_hit("strong", 0.8)],
    }

    def retrieve_for_query(query):
        return responses.get(query, [])

    hits, meta = agentic.retrieve_with_hops(
        retrieve_for_query,
        "q",
        k=5,
        threshold=0.5,
        max_hops=2,
        rewriter=FakeRewriter(["q rewritten"]),
    )
    assert meta["stop_reason"] == agentic.STOP_AFTER_REWRITE
    assert meta["hops"] == 2
    assert "q rewritten" in meta["queries"]
    assert hits[0]["chunk_id"] == "strong"


def test_cap_is_hard_and_reported():
    def retrieve_for_query(query):
        return [_hit("weak", 0.01)]

    hits, meta = agentic.retrieve_with_hops(
        retrieve_for_query,
        "q",
        k=5,
        threshold=0.5,
        max_hops=3,
        rewriter=FakeRewriter(["a", "b"]),
    )
    assert meta["stop_reason"] == agentic.STOP_CAP
    assert meta["hops"] == 3


def test_empty_retrieval_is_abstained_not_a_cap():
    _, meta = agentic.retrieve_with_hops(
        lambda query: [], "q", k=5, threshold=0.5, max_hops=1
    )
    assert meta["stop_reason"] == agentic.STOP_ABSTAINED


def test_rewriter_parses_json_and_refuses_garbage():
    class Client:
        def __init__(self, text):
            self.text = text

        def complete(self, model, messages, max_tokens=100, json_mode=False):
            return {"text": self.text, "tokens_in": 1, "tokens_out": 1}

    good = agentic.Rewriter(Client('{"queries": ["a", "b"]}'), model="m")
    assert good.rewrite("q", []) == ["a", "b"]
    bad = agentic.Rewriter(Client("no json here"), model="m")
    assert bad.rewrite("q", []) == []
    assert bad.last_stats["parse_failures"] == 1

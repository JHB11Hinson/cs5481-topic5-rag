from __future__ import annotations

from ragqa import evaluate, verify


def _entry(item_id, answerable, quote_in_chunk, abstained=False):
    text = (
        "the answer is 16 threads for merges"
        if quote_in_chunk
        else "unrelated content about dashboards"
    )
    retrieved = [
        {"chunk_id": "c1", "doc_id": "d", "rank": 1, "score": 0.9, "text": text},
        {"chunk_id": "c2", "doc_id": "d", "rank": 2, "score": 0.1, "text": "other text"},
    ]
    claim = {
        "claim_id": f"{item_id}-c1",
        "text": text,
        "chunk_id": "c1",
        "doc_id": "d",
        "span_start": 0,
        "span_end": len(text),
    }
    return {
        "item_id": item_id,
        "answerable": answerable,
        "abstained": abstained,
        "claims": [claim] if not abstained else [],
        "verdicts": verify.check_claims([claim], retrieved) if not abstained else [],
        "retrieved": retrieved,
        "quotes": ["the answer is 16 threads for merges"],
        "latency_ms": 1.0,
    }


def test_hit_rate_counts_quote_presence_not_chunk_identity():
    entries = [_entry("A1", True, True), _entry("A2", True, False)]
    metrics = evaluate.compute([], entries, 3)
    assert metrics["retrieval"]["hit_rate"] == 0.5
    assert metrics["retrieval"]["misses"] == ["A2"]


def test_containment_accepts_a_correct_span():
    text = "the answer is 16 threads for merges"
    claim = {"claim_id": "c", "text": text, "chunk_id": "c1", "doc_id": "d",
             "span_start": 0, "span_end": len(text)}
    verdicts = verify.check_claims([claim], [{"chunk_id": "c1", "text": text}])
    assert verdicts[0]["supported"] is True


def test_containment_flags_an_unretrieved_chunk():
    claim = {"claim_id": "c", "text": "x", "chunk_id": "zzz", "doc_id": "d",
             "span_start": 0, "span_end": 1}
    verdicts = verify.check_claims([claim], [{"chunk_id": "c1", "text": "x y"}])
    assert verdicts[0]["error_class"] == "chunk_not_retrieved"


def test_containment_flags_out_of_bounds_and_mismatched_text():
    text = "short chunk"
    out_of_bounds = {"claim_id": "a", "text": "x", "chunk_id": "c1", "doc_id": "d",
                     "span_start": 0, "span_end": 999}
    mismatch = {"claim_id": "b", "text": "not in chunk", "chunk_id": "c1", "doc_id": "d",
                "span_start": 0, "span_end": 5}
    verdicts = verify.check_claims([out_of_bounds, mismatch], [{"chunk_id": "c1", "text": text}])
    assert verdicts[0]["error_class"] == "span_out_of_bounds"
    assert verdicts[1]["error_class"] == "span_text_mismatch"


def test_abstention_counters():
    entries = [
        _entry("A1", True, True),
        _entry("A2", True, False, abstained=True),
        _entry("U1", False, False, abstained=True),
        _entry("U2", False, False, abstained=False),
    ]
    metrics = evaluate.compute([], entries, 3)
    assert metrics["abstention"]["abstained_answerable"] == 1
    assert metrics["abstention"]["over_abstain_rate"] == 0.5
    assert metrics["abstention"]["abstained_unanswerable"] == 1
    assert metrics["abstention"]["under_abstain"] == 1

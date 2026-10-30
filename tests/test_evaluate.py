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


def test_a_layer_that_judged_nothing_reports_no_precision():
    """0.0 would read as "every claim this layer saw was rejected"."""
    verdicts = [
        {"supported": True, "containment_ok": True, "span_start": 0,
         "nli_supported": None, "judge_supported": None},
        {"supported": True, "containment_ok": True, "span_start": 0,
         "nli_supported": None, "judge_supported": None},
    ]
    metrics = evaluate.grounding_metrics(verdicts)
    assert metrics["nli_judged"] == 0 and metrics["nli_precision"] is None, metrics
    assert metrics["judge_judged"] == 0 and metrics["judge_precision"] is None, metrics
    # Containment did see both claims, so its ratio is a real number.
    assert metrics["containment_precision"] == 1.0, metrics
    assert metrics["span_resolved_rate"] == 1.0, metrics

    nothing = evaluate.grounding_metrics([])
    assert nothing["containment_precision"] is None, nothing
    assert nothing["span_resolved_rate"] is None, nothing


def test_containment_precision_does_not_fall_back_to_the_judge_verdict():
    """The layers stay separate: a judge rejection is not a containment failure."""
    verdicts = [
        # Containment failed but a (hypothetical) judge said supported.
        {"supported": True, "containment_ok": False, "span_start": None,
         "nli_supported": None, "judge_supported": None},
        {"supported": False, "containment_ok": True, "span_start": 0,
         "nli_supported": False, "judge_supported": False},
    ]
    metrics = evaluate.grounding_metrics(verdicts)
    assert metrics["containment_pass"] == 1, metrics
    assert metrics["containment_precision"] == 0.5, metrics
    assert metrics["nli_precision"] == 0.0, metrics

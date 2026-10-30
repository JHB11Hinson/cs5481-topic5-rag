"""Ticket 10: the arithmetic that decides how far a judge can be trusted.

Two things are tested here, both at a seam rather than through the pipeline:

- the agreement arithmetic itself (`kappa`, `score_against_human`) against cases
  worked out by hand, because a metric that only agrees with itself proves
  nothing;
- the calibration data on disk, because a labelled row without a label (or a
  label without a justification) would silently become ground truth the judges
  are scored against.
"""

from __future__ import annotations

import json
import os

from ragqa import judges

NOTES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "notes",
    "judge-calibration.json",
)


def test_kappa_matches_a_hand_computed_two_by_two():
    # 3 true positives, 1 false positive, 2 false negatives, 4 true negatives.
    # observed agreement = 7/10 = 0.70
    # human  positive rate = 5/10, judge positive rate = 4/10
    # chance agreement  = 0.5*0.4 + 0.5*0.6 = 0.50
    # kappa             = (0.70 - 0.50) / (1 - 0.50) = 0.40
    human = [True, True, True, False, True, True, False, False, False, False]
    judge = [True, True, True, True, False, False, False, False, False, False]
    assert judges.score_against_human(human, judge)["tp"] == 3
    assert judges.score_against_human(human, judge)["fp"] == 1
    assert judges.score_against_human(human, judge)["fn"] == 2
    assert judges.score_against_human(human, judge)["tn"] == 4
    assert round(judges.kappa(human, judge), 6) == 0.4


def test_kappa_is_one_when_two_raters_agree_on_a_mixed_set():
    # observed agreement = 1.0, so kappa = 1.0 whatever the class balance is.
    # A constant pair of labellings cannot show this: see the next test.
    human = [True, False, True, True, False]
    assert judges.kappa(human, list(human)) == 1.0


def test_kappa_is_zero_when_chance_agreement_is_total():
    # Both raters say "supported" every time: agreement is 1.0 but it is also
    # exactly what chance predicts, so kappa must not be reported as 1.0.
    assert judges.kappa([True] * 6, [True] * 6) == 0.0


def test_kappa_rejects_mismatched_or_empty_labelling():
    for left, right in (([True, False], [True]), ([], [])):
        try:
            judges.kappa(left, right)
        except ValueError:
            continue
        raise AssertionError(f"kappa accepted {left!r} vs {right!r}")


def test_score_against_human_skips_claims_a_layer_never_judged():
    # The NLI layer is not asked about a claim that failed containment, so its
    # row is None and must leave every figure — a judge is neither credited nor
    # blamed for a claim it never saw.
    human = [True, True, False, False, True]
    nli = [True, False, False, True, None]
    score = judges.score_against_human(human, nli)
    assert score["n"] == 4 and score["skipped"] == 1
    assert score["precision"] == 0.5  # 1 true positive of 2 positive calls
    assert score["recall"] == 0.5  # 1 true positive of 2 supported claims
    assert score["agreement"] == 0.5  # 2 of 4 judged rows agree
    assert score["kappa"] == 0.0  # 0.5 observed against 0.5 chance


class _LegacyClient:
    """A client with the older signature: no `reasoning_effort` parameter."""

    def __init__(self):
        self.max_tokens = None

    def complete(self, model, messages, max_tokens=800, json_mode=True):
        self.max_tokens = max_tokens
        return {
            "text": '{"supported": true, "reason": "ok"}',
            "tokens_in": 1,
            "tokens_out": 1,
        }


class _EffortClient(_LegacyClient):
    def __init__(self):
        super().__init__()
        self.effort = None

    def complete(self, model, messages, max_tokens=800, json_mode=True, reasoning_effort=""):
        self.effort = reasoning_effort
        return super().complete(model, messages, max_tokens=max_tokens, json_mode=json_mode)


def test_llm_judge_gives_the_model_room_to_think():
    # `deepseek-v4-pro` answers through a thinking channel; a 200-token budget
    # can be consumed by reasoning alone and return empty content, which the
    # parser would score as "unsupported" and bias the judge toward false.
    client = _LegacyClient()
    judges.LLMJudge(client, "m").judge("claim", "evidence")
    assert client.max_tokens == 700


def test_llm_judge_passes_reasoning_effort_only_to_a_client_that_declares_it():
    modern = _EffortClient()
    judges.LLMJudge(modern, "m", reasoning_effort="none").judge("claim", "evidence")
    assert modern.effort == "none"

    legacy = _LegacyClient()
    outcome = judges.LLMJudge(legacy, "m", reasoning_effort="none").judge("claim", "evidence")
    assert outcome["supported"] is True


class _FakeCrossEncoder:
    """A checkpoint whose id2label order can be set per test."""

    def __init__(self, id2label, logits):
        import types

        self.model = types.SimpleNamespace(config=types.SimpleNamespace(id2label=id2label))
        self._logits = logits

    def predict(self, pairs):
        return [self._logits]


def test_nli_judge_reads_the_checkpoint_label_order_not_an_assumed_one():
    # MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli lists
    # [entailment, neutral, contradiction] — the reverse of the original MNLI
    # convention. Assuming the convention reads P(contradiction) as entailment
    # and inverts every verdict, which is exactly what the calibration caught.
    logits = [4.95, -1.87, -2.82]  # entailment wins by a wide margin
    judge = judges.NLIJudge(
        model_id="fake",
        threshold=0.5,
        model=_FakeCrossEncoder({0: "entailment", 1: "neutral", 2: "contradiction"}, logits),
    )
    assert judge.labels == ["entailment", "neutral", "contradiction"]
    outcome = judge.judge("premise", "hypothesis")
    assert outcome["label"] == "entailment"
    assert outcome["supported"] is True
    assert outcome["entailment"] > 0.99

    # The same logits under the documented MNLI order must read as contradiction.
    flipped = judges.NLIJudge(
        model_id="fake",
        threshold=0.5,
        model=_FakeCrossEncoder({0: "contradiction", 1: "neutral", 2: "entailment"}, logits),
    )
    assert flipped.judge("premise", "hypothesis")["label"] == "contradiction"


def test_llm_judge_reports_the_usage_of_each_call():
    # Per-claim usage is what lets a calibration price the claims it judged
    # instead of only the aggregate.
    client = _LegacyClient()
    outcome = judges.LLMJudge(client, "m").judge("claim", "evidence")
    assert outcome["tokens_in"] == 1 and outcome["tokens_out"] == 1


def _load_calibration():
    with open(NOTES, encoding="utf-8") as handle:
        return json.load(handle)


def test_calibration_rows_are_all_hand_labelled():
    payload = _load_calibration()
    rows = payload["claims"]
    assert len(rows) == 30
    required = {
        "claim_id",
        "item_id",
        "claim_text",
        "quote",
        "chunk_id",
        "doc_id",
        "source_run",
        "human_label",
        "justification",
        "origin",
    }
    seen = set()
    for row in rows:
        missing = required - set(row)
        assert not missing, f"{row.get('claim_id')} missing {sorted(missing)}"
        assert row["claim_id"] not in seen, f"duplicate claim_id {row['claim_id']}"
        seen.add(row["claim_id"])
        assert isinstance(row["human_label"], bool), row["claim_id"]
        assert len(row["justification"].strip()) > 10, row["claim_id"]
        assert row["origin"] in {"verbatim", "perturbed"}, row["claim_id"]
        if row["origin"] == "perturbed":
            assert row.get("derived_from"), row["claim_id"]
            assert row.get("edit"), row["claim_id"]
    supported = sum(1 for row in rows if row["human_label"])
    assert 0 < supported < len(rows), "a calibration set needs both labels"

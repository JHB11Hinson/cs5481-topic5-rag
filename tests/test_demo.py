"""The demo engine, tested through its public surface only.

Every test here runs the stub configuration (`configs/smoke.yaml`): fixture corpus,
hashed embedder, deterministic stub generator, in-memory index. No network, no GPU,
no model weights — the demo's job is to show what the pipeline can defend, and the
pipeline is the same one `ragqa.run` measures.
"""

from __future__ import annotations

import html

from ragqa import config as config_mod
from ragqa import demo

SMOKE = "configs/smoke.yaml"


def _engine():
    return demo.ChatEngine(config_mod.load(SMOKE))


def test_engine_builds_from_stub_config_without_network_or_gpu():
    engine = _engine()
    assert engine.config_name == "smoke"
    assert engine.chunk_count > 0
    assert engine.embedder.model_id == "stub-hashing"
    assert engine.generator.model_id == "stub-generator"
    assert engine.index_backend == "memory"


def test_answer_returns_one_citation_per_claim_from_retrieved_chunks():
    engine = _engine()
    response = engine.answer(
        "Which setting controls the number of threads used for background merges?"
    )

    assert response["abstained"] is False
    assert response["claims"], "an answerable fixture question produced no claims"
    retrieved_ids = {hit["chunk_id"] for hit in response["retrieved"]}
    for claim in response["claims"]:
        assert claim["chunk_id"] in retrieved_ids, "citation points outside the context"
        assert claim["verified"] is True, claim["error_class"]
        assert claim["marker"] == f"[{claim['marker_number']}]"
        assert claim["doc_title"], "a citation without a document title cannot be opened"
        assert claim["url"], "a citation without a URL cannot be opened"
        assert claim["heading_path"] is not None
        assert claim["span_text"], "a verified claim carries the text it rests on"


def test_near_miss_abstains_and_carries_the_best_chunk():
    engine = _engine()
    response = engine.answer(
        "What is the default value of replicated_deduplication_window in version 25.8?"
    )

    assert response["abstained"] is True
    assert response["claims"] == []
    best = response["best_chunk"]
    assert best is not None, "an abstention still shows what retrieval found"
    assert best["score"] > 0
    assert best["doc_title"] and best["url"]
    assert f"{best['score']:.3f}" in response["insufficiency"]

    screen = demo.render_answer(response)
    assert demo.ABSTAIN_MESSAGE.split(".")[0].lower() in screen.lower()
    assert best["doc_title"] in screen, "the best chunk is named on screen"
    assert f"{best['score']:.3f}" in screen, "its score is shown next to it"
    assert engine.config_name in screen, "the footer states the configuration served"
    assert f"{response['retrieval_ms']:.0f} ms" in screen


def test_citation_panel_carries_title_heading_url_and_marked_span():
    engine = _engine()
    response = engine.answer(
        "Which setting controls the number of threads used for background merges?"
    )
    claim = response["claims"][0]

    payload = engine.citation_payload(claim)
    props = engine.citation_props(payload)

    assert props["marker"] == claim["marker"]
    assert props["doc_title"] == claim["doc_title"]
    assert props["heading_path"] == claim["heading_path"]
    assert props["url"] == claim["url"]
    marked = props["chunk_html"].split("<mark>")[1].split("</mark>")[0]
    assert html.unescape(marked) == claim["span_text"]
    chunk = engine.chunks_by_id[claim["chunk_id"]]["text"]
    assert claim["span_text"] in chunk
    assert props["span_text"] == claim["span_text"]


class _LyingGenerator:
    """A generator that cites a real chunk but quotes text that is not in it."""

    model_id = "test-liar"

    def generate(self, item, retrieved, threshold, max_claims, min_claim_overlap=0.12,
                 extra_context=""):
        hit = retrieved[0]
        return {
            "answer_text": "A fabricated claim.",
            "claims": [
                {
                    "claim_id": f"{item['id']}-c1",
                    "text": "A fabricated claim.",
                    "quote": "this sentence is nowhere in the chunk it cites",
                    "chunk_id": hit["chunk_id"],
                    "doc_id": hit["doc_id"],
                }
            ],
            "citations": [{"chunk_id": hit["chunk_id"], "doc_id": hit["doc_id"]}],
            "abstained": False,
            "abstain_reason": "",
            "raw_response": "",
            "tokens_in": 0,
            "tokens_out": 0,
        }


def test_claim_whose_quote_is_not_in_its_chunk_is_not_shown_as_verified():
    engine = demo.ChatEngine(config_mod.load(SMOKE), generator=_LyingGenerator())
    response = engine.answer(
        "Which setting controls the number of threads used for background merges?"
    )

    assert len(response["claims"]) == 1
    claim = response["claims"][0]
    assert claim["verified"] is False
    assert claim["error_class"] == "quote_not_in_chunk"
    assert claim["marker"] == "", "an undefendable claim gets no citation marker"
    assert response["verified_claims"] == 0

    screen = demo.render_answer(response)
    assert "quote_not_in_chunk" in screen
    assert "[1]" not in screen
    try:
        engine.citation_payload(claim)
    except (KeyError, ValueError):
        pass
    else:
        raise AssertionError("nothing stops an unverified claim from being opened")

"""The sidebar's JSON API: conversations, bulk delete, replay, and asking.

These tests drive the handler functions directly — no socket, no browser — which is the
only way this surface gets tested at all in a session without one. The two properties
worth protecting are the ones a DeepSeek-shaped sidebar lives on: a bulk delete that
reports what it did not find instead of silently succeeding, and a conversation that comes
back byte-for-byte after a reload (transcript *and* citation payloads).
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List

from ragqa import demo, history, webapp


class FakeEngine:
    """Just enough of `ChatEngine` for the API layer."""

    config_name = "fake-cell"
    snapshot_id = "fake-snapshot"
    chunk_count = 3
    backend = "memory"
    cfg = {"retrieval.mode": "dense"}
    k = 5
    build_seconds = 1.0
    generator = type("Gen", (), {"model_id": "fake-generator"})()

    def answer(self, question: str) -> Dict[str, Any]:
        if question == "explode":
            raise RuntimeError("gateway closed")
        return {
            "question": question,
            "config_name": self.config_name,
            "answer_text": "It starts sealed.",
            "abstained": False,
            "abstain_reason": "",
            "claims": [
                {
                    "marker": "[1]",
                    "text": "It starts sealed.",
                    "verified": True,
                    "doc_title": "Seal",
                    "heading_path": "Seal > Overview",
                    "chunk_id": "c-1",
                    "doc_id": "docs/concepts/seal",
                    "span_start": 0,
                    "span_end": 5,
                }
            ],
            "verified_claims": 1,
            "retrieved": [],
            "retrieved_total": 1,
            "retrieval_ms": 12.0,
            "generation_ms": 34.0,
            "hops": 1,
            "hop_stop_reason": "hit_first_round",
            "best_chunk": None,
            "insufficiency": "",
        }

    def citation_payload(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "marker": claim["marker"],
            "chunk_id": claim["chunk_id"],
            "doc_id": claim["doc_id"],
            "span_start": claim["span_start"],
            "span_end": claim["span_end"],
        }

    def citation_props(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("chunk_id") != "c-1":
            raise KeyError(payload.get("chunk_id"))
        return {
            "marker": payload.get("marker", "[1]"),
            "doc_title": "Seal",
            "heading_path": "Seal > Overview",
            "url": "https://example.invalid/seal",
            "span_text": "seal",
            "chunk_html": "<mark>seal</mark>ed",
        }


def _install() -> None:
    directory = tempfile.mkdtemp(prefix="ragqa-web-")
    os.environ[demo._HISTORY_ENV] = os.path.join(directory, "history.sqlite")
    demo._HISTORY = None
    demo.install_engine(FakeEngine())


def test_config_reports_what_is_served():
    _install()
    config = webapp.api_config()
    assert config["configuration"] == "fake-cell"
    assert config["chunks"] == 3


def test_create_list_rename_and_open():
    _install()
    created = webapp.api_create("by hand")
    assert created["id"].startswith("c-")
    listing = webapp.api_list()
    assert [row["id"] for row in listing] == [created["id"]]

    renamed = webapp.api_rename(created["id"], "renamed on purpose")
    assert renamed["title"] == "renamed on purpose"

    opened = webapp.api_messages(created["id"])
    assert opened["conversation"]["title"] == "renamed on purpose"
    assert opened["messages"] == []


def test_bulk_delete_reports_missing_ids_instead_of_pretending():
    _install()
    first = webapp.api_create("one")
    second = webapp.api_create("two")
    result = webapp.api_delete([first["id"], second["id"], "c-nosuch"])
    assert set(result["deleted"]) == {first["id"], second["id"]}
    assert result["missing"] == ["c-nosuch"]
    assert webapp.api_list() == []


def test_bulk_delete_refuses_an_empty_selection():
    _install()
    try:
        webapp.api_delete([])
    except webapp.ApiError as error:
        assert error.status == 400
    else:
        raise AssertionError("an empty bulk delete was accepted")


def test_asking_stores_the_transcript_and_the_citation_payload():
    _install()
    conversation = webapp.api_create()
    result = webapp.api_ask(conversation["id"], "What state does a Vault server start in?")
    assert result["response"]["claims"][0]["marker"] == "[1]"
    assert result["payload"]["claims"][0]["citation"]["chunk_id"] == "c-1"

    replayed = webapp.api_messages(conversation["id"])
    roles = [message["role"] for message in replayed["messages"]]
    assert roles == ["user", "assistant"]
    assert replayed["messages"][1]["payload"]["claims"][0]["marker"] == "[1]"
    # The untitled conversation took its name from the question.
    assert replayed["conversation"]["title"].startswith("What state")


def test_a_failing_answer_surfaces_as_an_api_error_and_leaves_the_question_stored():
    _install()
    conversation = webapp.api_create()
    try:
        webapp.api_ask(conversation["id"], "explode")
    except RuntimeError as error:
        assert "gateway closed" in str(error)
    else:
        raise AssertionError("a failing answer was reported as success")
    turns = history.ConversationStore(os.environ[demo._HISTORY_ENV]).messages(conversation["id"])
    assert len(turns) == 1


def test_citation_props_reject_an_unknown_chunk():
    _install()
    try:
        webapp.api_citation({"chunk_id": "c-nope"})
    except webapp.ApiError as error:
        assert error.status == 404
    else:
        raise AssertionError("a citation for a chunk outside the index was served")


def test_the_static_assets_exist_and_are_served_from_the_asset_root():
    root = webapp.ASSET_ROOT
    for name in ("index.html", "app.js", "app.css"):
        assert os.path.isfile(os.path.join(root, name)), name
    with open(os.path.join(root, "app.js"), encoding="utf-8") as handle:
        source = handle.read()
    assert "/api/conversations" in source
    assert "delete" in source.lower()

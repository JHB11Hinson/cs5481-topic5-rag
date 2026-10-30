from __future__ import annotations

import re

from ragqa import chunk as chunk_mod

DOC = {
    "doc_id": "demo/doc",
    "heading_path": "Demo",
    "text": (
        "# Demo\n\n"
        "## Alpha\n\n"
        "First sentence about pools. Second sentence about threads. Third about limits.\n\n"
        "## Beta\n\n"
        "A table follows.\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    ),
}


def test_fixed_chunks_are_deterministic():
    first = chunk_mod.chunk_fixed(DOC, 8, 2)
    second = chunk_mod.chunk_fixed(DOC, 8, 2)
    assert [c["chunk_id"] for c in first] == [c["chunk_id"] for c in second]


def test_fixed_chunks_cover_the_document():
    chunks = chunk_mod.chunk_fixed(DOC, 8, 2)
    assert chunks[0]["char_start"] == 0
    last_word = DOC["text"].rstrip().split()[-1]
    assert last_word in chunks[-1]["text"]
    for chunk in chunks:
        assert chunk["text"] == DOC["text"][chunk["char_start"]: chunk["char_end"]]
        assert chunk["token_count"] > 0


def test_fixed_step_uses_overlap():
    chunks = chunk_mod.chunk_fixed(DOC, 8, 2)
    assert len(chunks) > 1
    words_first = chunks[0]["text"].split()
    words_second = chunks[1]["text"].split()
    step = len(words_first) - 2
    assert words_first[step:step + 2] == words_second[:2]


def test_recursive_children_have_parents_that_cover_them():
    chunks = chunk_mod.chunk_recursive(DOC, 6, 12)
    children = [c for c in chunks if c["kind"] == "child"]
    parents = {c["chunk_id"]: c for c in chunks if c["kind"] == "parent"}
    assert children and parents
    for child in children:
        assert child["parent_id"] in parents
        parent = parents[child["parent_id"]]
        assert parent["char_start"] <= child["char_start"]
        assert parent["char_end"] >= child["char_end"]


def test_recursive_splits_a_sentence_longer_than_the_limit():
    long_doc = {
        "doc_id": "demo/long",
        "text": "word " * 40 + "end.",
        "heading_path": "",
    }
    chunks = chunk_mod.chunk_recursive(long_doc, 6, 50)
    children = [c for c in chunks if c["kind"] == "child"]
    assert len(children) > 1
    assert all(c["token_count"] <= 6 for c in children)


def test_heading_path_is_carried():
    chunks = chunk_mod.chunk_recursive(DOC, 20, 80)
    paths = {c["heading_path"] for c in chunks if c["kind"] == "child"}
    assert any("Alpha" in path for path in paths)
    assert any("Beta" in path for path in paths)


def test_stats_counts_parents_and_children():
    chunks = chunk_mod.chunk_recursive(DOC, 6, 12)
    stats = chunk_mod.stats(chunks)
    assert stats["chunks"] == len([c for c in chunks if c["kind"] == "child"])
    assert stats["parents"] == len([c for c in chunks if c["kind"] == "parent"])

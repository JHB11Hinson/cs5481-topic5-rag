from __future__ import annotations

import math

from ragqa import embed, index, retrieve

TEXTS = {
    "c1": "background_pool_size sets the number of threads performing background merges",
    "c2": "parts are immutable and merges replace several parts with one",
    "c3": "unrelated text about dashboards and panels",
}
CHUNKS = {
    key: {"chunk_id": key, "doc_id": "d", "text": value, "parent_id": ""}
    for key, value in TEXTS.items()
}


def _built():
    embedder = embed.StubEmbedder(dim=128)
    vectors = embedder.embed([CHUNKS[key]["text"] for key in CHUNKS])
    store = index.MemoryIndex()
    store.add(list(CHUNKS), vectors)
    return embedder, store


def test_vectors_are_unit_normalised():
    embedder = embed.StubEmbedder(dim=64)
    vector = embedder.embed(["merges and threads"])[0]
    norm = math.sqrt(sum(value * value for value in vector))
    assert abs(norm - 1.0) < 1e-9


def test_embedding_is_deterministic_across_instances():
    a = embed.StubEmbedder(dim=64).embed(["same text here"])[0]
    b = embed.StubEmbedder(dim=64).embed(["same text here"])[0]
    assert a == b


def test_dense_retrieval_ranks_the_matching_chunk_first():
    embedder, store = _built()
    query = embedder.embed(["how many threads run background merges"])[0]
    hits = retrieve.retrieve(store, CHUNKS, query, "dense", 3)
    assert hits[0]["chunk_id"] == "c1"
    assert [hit["rank"] for hit in hits] == [1, 2, 3]
    assert hits[0]["score"] > hits[-1]["score"]


def test_modes_refuse_to_run_without_their_inputs():
    embedder, store = _built()
    query = embedder.embed(["anything"])[0]
    for mode in ("hybrid", "rerank"):
        try:
            retrieve.retrieve(store, CHUNKS, query, mode, 3, query="anything")
        except ValueError as exc:
            assert "BM25" in str(exc)
        else:
            raise AssertionError(f"mode {mode} ran without a sparse index")


def test_unknown_mode_is_rejected():
    embedder, store = _built()
    query = embedder.embed(["anything"])[0]
    try:
        retrieve.retrieve(store, CHUNKS, query, "magic", 3)
    except ValueError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("unknown mode was accepted")


def test_hybrid_keeps_both_branch_ranks():
    from ragqa import sparse

    embedder, store = _built()
    lexical = sparse.BM25Index()
    lexical.add(list(CHUNKS), [CHUNKS[key]["text"] for key in CHUNKS])
    query_vector = embedder.embed(["background merges threads"])[0]
    hits = retrieve.retrieve(
        store, CHUNKS, query_vector, "hybrid", 3,
        query="background merges threads", sparse=lexical,
    )
    assert hits[0]["chunk_id"] == "c1"
    assert "dense" in hits[0]["branches"]
    assert "sparse" in hits[0]["branches"]


def test_empty_index_returns_nothing():
    store = index.MemoryIndex()
    assert store.search([0.0, 0.0], 3) == []

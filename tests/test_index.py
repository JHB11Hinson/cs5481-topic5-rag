from __future__ import annotations

import shutil
import tempfile

from ragqa import embed, index


def test_qdrant_local_mode_round_trip():
    path = tempfile.mkdtemp()
    try:
        embedder = embed.StubEmbedder(dim=32)
        texts = {
            "c1": "background merges and threads",
            "c2": "table parts and merges",
            "c3": "dashboards and panels",
        }
        vectors = embedder.embed(list(texts.values()))
        store = index.QdrantIndex(path, "test")
        store.add(list(texts), vectors)
        assert store.count() == 3

        query = embedder.embed(["background merges"])[0]
        hits = store.search(query, 2)
        assert len(hits) == 2
        assert hits[0][0] == "c1"
        assert hits[0][1] >= hits[1][1]
        assert store.size_bytes() > 0
        store.close()
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_qdrant_rebuild_is_idempotent():
    path = tempfile.mkdtemp()
    try:
        embedder = embed.StubEmbedder(dim=16)
        ids = ["a", "b"]
        vectors = embedder.embed(["alpha text", "beta text"])
        store = index.QdrantIndex(path, "rebuild")
        store.add(ids, vectors)
        store.add(ids, vectors)
        assert store.count() == 2
        store.close()
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_point_ids_are_stable():
    assert index.point_id("c-abc") == index.point_id("c-abc")
    assert index.point_id("c-abc") != index.point_id("c-abd")

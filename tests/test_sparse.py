from __future__ import annotations

from ragqa import sparse


TEXTS = {
    "c1": "background_pool_size sets the number of threads for background merges",
    "c2": "max_concurrent_queries limits simultaneous queries",
    "c3": "replicated_deduplication_window controls insert block deduplication",
}


def _index():
    index = sparse.BM25Index()
    index.add(list(TEXTS), list(TEXTS.values()))
    return index


def test_exact_identifier_is_found():
    index = _index()
    hits = index.search("replicated_deduplication_window", 3)
    assert hits and hits[0][0] == "c3"


def test_scores_are_positive_and_ordered():
    index = _index()
    hits = index.search("threads background merges", 3)
    assert hits[0][0] == "c1"
    scores = [score for _, score in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(score > 0 for score in scores)


def test_unknown_term_returns_nothing():
    index = _index()
    assert index.search("nonexistentterm", 3) == []


def test_rrf_fusion_prefers_items_ranked_by_both_branches():
    dense = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    lexical = [("b", 12.0), ("d", 9.0)]
    fused = sparse.rrf_fuse({"dense": dense, "sparse": lexical}, rrf_k=60, limit=4)
    order = [item_id for item_id, _, _ in fused]
    assert order[0] == "b", "an item found by both branches should win"
    assert order.index("a") < order.index("d")
    ranks = dict((item_id, ranks) for item_id, _, ranks in fused)
    assert ranks["b"] == {"dense": 2, "sparse": 1}


def test_rrf_rewards_agreement_over_a_single_strong_hit():
    dense = [("x", 100.0), ("y", 1.0)]
    lexical = [("y", 100.0), ("x", 1.0)]
    fused = sparse.rrf_fuse({"dense": dense, "sparse": lexical}, rrf_k=60, limit=2)
    assert abs(fused[0][1] - fused[1][1]) < 1e-9, "symmetric ranks must fuse symmetrically"

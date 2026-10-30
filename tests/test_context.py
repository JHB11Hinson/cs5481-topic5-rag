from __future__ import annotations

from ragqa import context as context_mod
from ragqa.sparse import BM25Index


class FakeClient:
    """Deterministic stand-in for the cheap model; counts real calls."""

    def __init__(self, template="This page is about {keyword}."):
        self.template = template
        self.calls = 0
        self.seen = []

    def complete(self, model, messages, max_tokens=100, json_mode=False):
        self.calls += 1
        self.seen.append(messages)
        prompt = messages[-1]["content"]
        keyword = prompt.split("Section:")[-1].split("\n")[0].strip() or "the excerpt"
        return {"text": self.template.format(keyword=keyword), "tokens_in": 12, "tokens_out": 8}


def _chunks():
    return [
        {
            "chunk_id": "c1",
            "doc_id": "docs/concepts/seal",
            "kind": "child",
            "heading_path": "Seal > Unseal",
            "text": "The default is false.",
            "char_start": 0,
            "char_end": 20,
        },
        {
            "chunk_id": "c2",
            "doc_id": "docs/concepts/seal",
            "kind": "child",
            "heading_path": "Seal > Unseal",
            "text": "Unsealing requires a quorum of key shares.",
            "char_start": 21,
            "char_end": 66,
        },
    ]


def _docs():
    return {"docs/concepts/seal": {"doc_id": "docs/concepts/seal", "text": "doc" * 50}}


def test_prompt_is_stable_for_identical_inputs():
    first = context_mod.prompt_for("d", "A > B", "text", "before", "after")
    second = context_mod.prompt_for("d", "A > B", "text", "before", "after")
    assert first == second
    assert "Document: d" in first and "Section: A > B" in first


def test_prompt_changes_when_context_changes():
    a = context_mod.prompt_for("d", "A", "text", "before")
    b = context_mod.prompt_for("d", "A", "text", "different before")
    assert a != b


def test_prefix_is_cached_and_a_rerun_reports_full_hits():
    import os
    import tempfile

    cache = os.path.join(tempfile.mkdtemp(prefix="ragqa-prefix-"), "p.sqlite")
    chunks = _chunks()
    client = FakeClient()
    first = context_mod.PrefixGenerator(client, model="cheap", cache_path=cache)
    stats_one = first.generate(chunks, _docs())
    assert stats_one["misses"] == 2 and stats_one["hits"] == 0
    assert client.calls == 2

    second = context_mod.PrefixGenerator(FakeClient(), model="cheap", cache_path=cache)
    stats_two = second.generate(chunks, _docs())
    assert stats_two["hits"] == 2 and stats_two["misses"] == 0
    assert stats_two["tokens_in"] == 0


def test_contextual_text_keeps_the_original_verbatim():
    chunks = _chunks()
    generator = context_mod.PrefixGenerator(FakeClient(), model="cheap", cache_path=":memory:")
    generator.generate(chunks, _docs())
    for chunk in chunks:
        assert chunk["contextual_text"].endswith(chunk["text"])
        assert chunk["prefix"]
        assert chunk["text"] == _chunks()[0]["text"] or chunk["chunk_id"] == "c2"


def test_sanitize_strips_markdown_and_bounds_length():
    assert context_mod.sanitize("**Hello**\n\nworld") == "Hello world"
    long = "word " * 300
    assert len(context_mod.sanitize(long)) <= context_mod.MAX_PREFIX_CHARS


def test_sparse_index_terms_include_prefix_tokens():
    """A token that exists only in the prefix must be findable by BM25 (ticket 07)."""
    chunks = _chunks()
    generator = context_mod.PrefixGenerator(
        FakeClient(template="Rotation procedure for the vaultunsealkeyquorum flow."),
        model="cheap",
        cache_path=":memory:",
    )
    generator.generate(chunks, _docs())
    index = BM25Index()
    index.add([c["chunk_id"] for c in chunks], [c["contextual_text"] for c in chunks])
    hits = index.search("vaultunsealkeyquorum", 5)
    assert hits, "prefix-only token was not indexed"
    plain = BM25Index()
    plain.add([c["chunk_id"] for c in chunks], [c["text"] for c in chunks])
    assert not plain.search("vaultunsealkeyquorum", 5)

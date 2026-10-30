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


class EmptyClient:
    """What an emptied token budget returns: no content, and a full reasoning spend."""

    def complete(self, model, messages, max_tokens=100, json_mode=False):
        return {"text": "   ", "tokens_in": 12, "tokens_out": 120}


def test_empty_model_content_raises_and_is_never_cached():
    """An empty completion must stop the run, not be cached as an empty prefix.

    This fired once in production: with the thinking channel on, the model spent the
    whole token budget on reasoning and returned no content. Caching "" made
    `contextual_text` byte-identical to the plain level while the config declared a
    prefix level, so an A/B cell silently measured the thing it was compared against.
    """
    import os
    import tempfile

    import pytest

    cache = os.path.join(tempfile.mkdtemp(prefix="ragqa-prefix-"), "p.sqlite")
    generator = context_mod.PrefixGenerator(EmptyClient(), model="cheap", cache_path=cache)
    with pytest.raises(context_mod.EmptyPrefixError):
        generator.generate(_chunks(), _docs())
    assert context_mod.PrefixCache(cache).count() == 0


def test_prefix_lengths_are_measured_on_a_full_hit_rerun():
    """The p50/max summary describes the chunks the invocation saw, hits included.

    A rerun reports 100% cache hits and spends no tokens, so measuring only this
    invocation's misses published `prefix_p50_chars: 0` on a run that had 2,203
    real prefixes behind it.
    """
    import os
    import tempfile

    cache = os.path.join(tempfile.mkdtemp(prefix="ragqa-prefix-"), "p.sqlite")
    first = context_mod.PrefixGenerator(FakeClient(), model="cheap", cache_path=cache)
    first.generate(_chunks(), _docs())

    chunks = _chunks()
    second = context_mod.PrefixGenerator(FakeClient(), model="cheap", cache_path=cache)
    stats = second.generate(chunks, _docs())
    assert stats["hits"] == 2 and stats["misses"] == 0
    # Ground truth: the prefixes the run actually carried, not a recomputation of
    # the summary's own arithmetic.
    carried = sorted(len(chunk["prefix"]) for chunk in chunks)
    summary = second.summary()
    assert summary["prefix_p50_chars"] == carried[len(carried) // 2]
    assert summary["prefix_max_chars"] == carried[-1]
    assert summary["prefix_p50_chars"] > 0


def test_summary_reports_none_when_no_chunk_was_measured():
    generator = context_mod.PrefixGenerator(FakeClient(), model="cheap", cache_path=":memory:")
    generator.generate([], _docs())
    summary = generator.summary()
    assert summary["prefix_p50_chars"] is None
    assert summary["prefix_max_chars"] is None


def test_cache_migrates_a_database_without_the_length_column():
    """An existing cache database must keep working, and keep its rows."""
    import os
    import sqlite3
    import tempfile

    path = os.path.join(tempfile.mkdtemp(prefix="ragqa-prefix-"), "p.sqlite")
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE prefixes ("
        " key TEXT PRIMARY KEY, model TEXT NOT NULL, prompt_version TEXT NOT NULL,"
        " prefix TEXT NOT NULL, tokens_in INTEGER, tokens_out INTEGER)"
    )
    old.execute(
        "INSERT INTO prefixes VALUES ('k', 'cheap', 'v1@default', 'a legacy prefix', 10, 4)"
    )
    old.commit()
    old.close()

    cache = context_mod.PrefixCache(path)
    assert cache.get("k") == "a legacy prefix"
    # A row written before the column existed still reports a real length.
    assert cache.get_chars("k") == len("a legacy prefix")
    cache.put("k2", "cheap", "v1@default", "a new prefix", 3, 2)
    assert cache.get_chars("k2") == len("a new prefix")


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

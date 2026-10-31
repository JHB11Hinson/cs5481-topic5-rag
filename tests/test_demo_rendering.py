"""Only the rendering rules: a JSON blob must never reach a reader."""

from ragqa.demo import _prose_excerpt, render_answer


def test_a_json_chunk_yields_no_excerpt():
    assert _prose_excerpt('{"auth": {"accessor": "hmac-sha256:abc"}}') == ""


def test_a_json_chunk_inside_a_fence_is_removed_whole():
    text = "before the block\n```json\n{\"a\": 1}\n```\nafter the fence."
    excerpt = _prose_excerpt(text)
    assert "before the block" in excerpt
    assert "after the fence" in excerpt
    assert "{" not in excerpt and "```" not in excerpt


def test_prose_passes_through_and_is_capped():
    text = "Vault starts in a sealed state. It cannot decrypt data on the storage."
    assert _prose_excerpt(text).startswith("Vault starts in a sealed state.")
    long = "This sentence is long enough to matter. " * 20
    excerpt = _prose_excerpt(long, limit=120)
    assert len(excerpt) <= 121


def _response(**overrides):
    base = {
        "abstained": False,
        "abstain_reason": "",
        "claims": [
            {"marker": "[1]", "text": "It starts sealed.", "verified": True,
             "doc_title": "Seal", "heading_path": "Seal › Overview"},
        ],
        "best_chunk": {"doc_title": "Seal", "heading_path": "Seal › Overview",
                       "doc_id": "d", "url": "u", "chunk_id": "c-1",
                       "score": 0.42, "text": "Vault starts sealed."},
        "hops": 1,
        "retrieval_ms": 12.0,
        "generation_ms": 34.0,
        "config_name": "cell",
        "insufficiency": "",
    }
    base.update(overrides)
    return base


def test_the_answer_carries_no_instrumentation():
    markdown = render_answer(_response())
    assert "It starts sealed. [1]" in markdown
    for banned in ("ms", "chunk", "c-1", "0.42", "configuration", "score"):
        assert banned not in markdown, banned


def test_the_abstention_is_one_sentence_and_a_pointer_not_a_dump():
    markdown = render_answer(
        _response(
            abstained=True,
            abstain_reason="The question is a greeting; no claim can be supported.",
            best_chunk={
                "doc_title": "Audit log entry schema",
                "heading_path": "Full entry examples",
                "doc_id": "d",
                "url": "u",
                "chunk_id": "c-bc",
                "score": 0.021,
                "text": '```json\n{"auth": {"accessor": "hmac-sha256:3348"}}\n```',
            },
        )
    )
    assert "Audit log entry schema" in markdown
    assert "hmac-sha256" not in markdown
    assert "```" not in markdown
    assert "0.021" not in markdown and "c-bc" not in markdown


def test_withheld_claims_are_counted_not_dumped():
    markdown = render_answer(
        _response(
            claims=[
                {"marker": "[1]", "text": "Kept.", "verified": True,
                 "doc_title": "D", "heading_path": ""},
                {"marker": "[2]", "text": "Dropped.", "verified": False,
                 "doc_title": "D", "heading_path": "",
                 "error_class": "quote_not_in_chunk", "chunk_id": "c-9", "detail": "x"},
            ]
        )
    )
    assert "Kept. [1]" in markdown
    assert "Dropped." not in markdown
    assert "1 further claim(s) were withheld" in markdown
    assert "quote_not_in_chunk" not in markdown and "c-9" not in markdown

from __future__ import annotations

from ragqa import chunk as chunk_mod

DOC_WITH_TABLE_AND_CODE = {
    "doc_id": "demo/units",
    "heading_path": "Demo",
    "text": (
        "# Demo\n\n"
        "## Alpha\n\n"
        "First sentence about pools. Second sentence about threads.\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n\n"
        "```bash\nvault status\nvault operator init\n```\n\n"
        "## Beta\n\n"
        "Third sentence about limits.\n"
    ),
}


def test_table_is_atomic():
    chunks = chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 4, 40)
    children = [c for c in chunks if c["kind"] == "child"]
    tables = [c for c in children if c["text"].lstrip().startswith("|")]
    assert len(tables) == 1
    assert tables[0]["text"].count("| 1 | 2 |") == 1
    assert "| 3 | 4 |" in tables[0]["text"]


def test_code_block_is_atomic():
    chunks = chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 4, 40)
    children = [c for c in chunks if c["kind"] == "child"]
    fences = [c for c in children if "```" in c["text"]]
    assert len(fences) == 1
    assert "vault operator init" in fences[0]["text"]


def test_children_accumulate_across_headings():
    chunks = chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 200, 400)
    children = [c for c in chunks if c["kind"] == "child"]
    joined = [c for c in children if "First sentence" in c["text"]]
    assert len(joined) == 1
    assert "Third sentence" in joined[0]["text"], "small units must merge across a heading change"
    assert joined[0]["heading_path"].startswith("Demo > Alpha")


def test_parents_group_consecutive_children():
    chunks = chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 10, 20)
    children = [c for c in chunks if c["kind"] == "child"]
    parents = {c["chunk_id"]: c for c in chunks if c["kind"] == "parent"}
    assert len(parents) >= 2
    for child in children:
        parent = parents[child["parent_id"]]
        assert parent["char_start"] <= child["char_start"]
        assert parent["char_end"] >= child["char_end"]
        assert parent["token_count"] <= 60, "parent budget is a cap, not a target"


def test_fixed_window_splits_a_table_that_recursive_keeps():
    fixed = [
        c for c in chunk_mod.chunk_fixed(DOC_WITH_TABLE_AND_CODE, 3, 0)
        if "|" in c["text"]
    ]
    assert len(fixed) >= 2, "the fixed window is expected to cut the table across chunks"
    recursive = [
        c for c in chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 200, 400)
        if c["kind"] == "child" and "| 1 | 2 |" in c["text"]
    ]
    assert len(recursive) == 1 and "| 3 | 4 |" in recursive[0]["text"]


def test_stats_reports_the_strategy_signature():
    chunks = chunk_mod.chunk_recursive(DOC_WITH_TABLE_AND_CODE, 10, 40)
    summary = chunk_mod.stats(chunks, 10)
    assert summary["chunks"] > 0
    assert 0.0 < summary["share_containing_table_row"] < 1.0
    assert summary["share_containing_code_fence"] > 0.0
    assert summary["share_over_budget"] >= 0.0

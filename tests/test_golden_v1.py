"""The golden set is only worth what its validator can catch (ticket 08).

These tests sit at the same seam the CLI uses: `ragqa.corpus.load_documents` feeds
`ragqa.golden.validate`, which is exactly what `python -m ragqa golden validate`
calls. The first test proves a bad quote is rejected; the rest prove `golden/v1.jsonl`
carries the properties the spec promises.

The corpus snapshot is gitignored, so the corpus-anchored test is skipped when it is
not checked out (it always is in the shared checkout, and in CI). The structural
checks need nothing but the emitted JSONL, so they run everywhere.
"""

from __future__ import annotations

import json
import os
import tempfile

from ragqa import golden
from ragqa.corpus import load_documents

DEFAULT_CORPUS = "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"
GOLDEN_V1 = "golden/v1.jsonl"
DRAFTED_BY = "llm:deepseek-v4.1-flash@2026-10-30"
VERIFIED_BY = "automated:corpus-anchored"
STRATA = {"fact_lookup": 10, "param_value": 8, "table_content": 8, "multi_hop": 8, "concept": 6}
NEGATIVES = 20


def _write(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _item(**overrides):
    item = {
        "id": "A001",
        "answerable": True,
        "type": "fact_lookup",
        "question": "What state does a Vault server start in when it is launched?",
        "reference_answer": "It starts in a sealed state.",
        "evidence": [{"doc_id": "docs/concepts/seal", "quote": "it starts in a sealed state"}],
        "difficulty": "easy",
        "provenance": {"drafted_by": "human", "verified_by": "human", "edits": ""},
        "tags": ["seal"],
    }
    item.update(overrides)
    return item


def test_validator_rejects_a_quote_that_drifted_from_the_corpus():
    docs = [
        {"doc_id": "docs/concepts/seal", "text": "# Seal\n\nWhen you start a Vault server, it starts in a sealed state.\n"},
        {"doc_id": "docs/concepts/lease", "text": "# Lease\n\nAll dynamic secrets in Vault are required to have a lease.\n"},
    ]
    broken = _item(evidence=[{"doc_id": "docs/concepts/seal", "quote": "it starts in a locked state"}])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "broken.jsonl")
        _write(path, [broken])
        problems = golden.validate(path, docs, strict_quotas=False)
    assert problems, "a quote that is not in the document must fail validation"
    assert any("not found verbatim" in problem for problem in problems), problems

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "good.jsonl")
        _write(path, [_item()])
        assert golden.validate(path, docs, strict_quotas=False) == []


def test_validator_rejects_a_quote_that_is_not_unique_and_a_bad_doc_id():
    shared = "All dynamic secrets in Vault are required to have a lease."
    docs = [
        {"doc_id": "docs/concepts/lease", "text": shared + "\n"},
        {"doc_id": "docs/concepts/lease-faq", "text": shared + "\n"},
    ]
    duplicated = _item(evidence=[{"doc_id": "docs/concepts/lease", "quote": shared}])
    unknown_doc = _item(evidence=[{"doc_id": "docs/concepts/nope", "quote": shared}])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "dupes.jsonl")
        _write(path, [duplicated])
        problems = golden.validate(path, docs, strict_quotas=False)
        assert any("not unique" in problem for problem in problems), problems

        path = os.path.join(tmp, "unknown.jsonl")
        _write(path, [unknown_doc])
        problems = golden.validate(path, docs, strict_quotas=False)
        assert any("not in corpus" in problem for problem in problems), problems


def test_v1_meets_the_quota_table_and_structural_rules():
    items = golden.load(GOLDEN_V1)
    assert len(items) == sum(STRATA.values()) + NEGATIVES

    counts = {}
    for item in items:
        if item.get("answerable", True):
            counts[item["type"]] = counts.get(item["type"], 0) + 1
    assert counts == STRATA, counts
    assert sum(1 for item in items if not item.get("answerable", True)) == NEGATIVES

    ids = [item["id"] for item in items]
    assert ids[: sum(STRATA.values())] == [f"A{n:03d}" for n in range(1, 41)]
    assert ids[sum(STRATA.values()) :] == [f"U{n:03d}" for n in range(1, 21)]

    for item in items:
        if not item.get("answerable", True):
            assert item["type"] == "near_miss", item["id"]
            for field in ("why_unanswerable", "near_miss_doc", "difficulty"):
                assert item.get(field), f"{item['id']}: missing {field}"
            continue
        if item["type"] == "table_content":
            assert item["evidence"], item["id"]
            for evidence in item["evidence"]:
                assert "|" in evidence["quote"], f"{item['id']}: quote is not a table row"
        if item["type"] == "multi_hop":
            doc_ids = {evidence["doc_id"] for evidence in item["evidence"]}
            assert len(item["evidence"]) >= 2, f"{item['id']}: needs two evidence entries"
            assert len(doc_ids) == len(item["evidence"]), f"{item['id']}: doc_ids must be distinct"


def test_v1_provenance_is_honest_about_who_drafted_and_verified():
    items = golden.load(GOLDEN_V1)
    for item in items:
        provenance = item["provenance"]
        assert provenance["drafted_by"] == DRAFTED_BY, f"{item['id']}: {provenance['drafted_by']}"
        assert provenance["verified_by"] == VERIFIED_BY, f"{item['id']}: {provenance['verified_by']}"


def test_v1_passes_the_validation_the_cli_runs_against_the_corpus_snapshot():
    corpus = os.environ.get("RAGQA_CORPUS", DEFAULT_CORPUS)
    if not os.path.exists(corpus):
        # The snapshot is gitignored; run this in the shared checkout, not a bare worktree.
        return
    docs = load_documents(corpus)
    assert golden.validate(GOLDEN_V1, docs, strict_quotas=True) == []

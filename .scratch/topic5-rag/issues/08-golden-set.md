# 08: Golden QA Set v1 with a validator that can fail

**What to build:** a 60-item golden set — 40 answerable across five strata, 20 deliberate near-misses — that a validator checks before any experiment consumes it. Evidence is anchored as document plus quoted sentence, so re-chunking cannot break the set.

**Blocked by:** 02, 06.

**Status:** done — v1 frozen at 60 items

`golden/v0.jsonl` holds 20 items (10 answerable across fact_lookup / param_value / table_content / multi_hop / concept, 10 near-misses split into version drift, deployment-specific, sibling product, composition, procedure gap, and commercial). Validator reports 0 problems: every quote is verbatim in its document and unique in the corpus.

Quotes are never retyped. `golden/spec_v0.json` names each piece of evidence by `(doc_id, keyword)`, and `scripts/golden_emit.py` extracts the sentence or table row from the corpus. A quote that drifts from the corpus is the one defect that silently devalues every number downstream, so the pipeline makes that defect impossible rather than reviewing for it.

Remaining for v1: 40 more answerable items to meet the strata quotas in `golden/SPEC.md` (currently 3 fact_lookup / 3 param_value / 2 table_content / 1 multi_hop / 1 concept), and 10 more near-misses.

- [x] `golden/v0.jsonl` (20 items) exists before the first end-to-end run
- [x] `golden/v1.jsonl` meets the quota table in `golden/SPEC.md`
- [x] `ragqa golden validate` implements all six checks, including quote-in-document and quote-uniqueness, and exits non-zero with a per-item report
- [x] Every quote verifies by character search after whitespace normalisation
- [x] Every item carries provenance; the count of human-edited drafts is reported with the drafting model and date
- [x] `multi_hop` items cite two distinct documents; `table_content` items resolve to a real table row

## Resolution

`golden/v1.jsonl` carries 60 items: `fact_lookup` 10, `param_value` 8,
`table_content` 8, `multi_hop` 8, `concept` 6, near-miss 20. The validator is green:

```
$ python -m ragqa golden validate golden/v1.jsonl --strict-quotas \
    --corpus=data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl
golden/v1.jsonl: ok against 1268 documents
```

Quotes are extracted from the corpus by keyword (`golden/spec_v1.json` holds anchors
only, never quote text), so a retyped quote is not possible. Six items were revised
before ship and the log is in `notes/golden-v1-authoring.md`.

Two facts a reader must not paper over. `verified_by` is `automated:corpus-anchored`
on all 60 items: the quotes are provably in their documents, the *questions* were not
reviewed by a human. And v0 has a real defect that stays in v0 because a golden set is
immutable — its U005 is answerable, since the corpus does contain
`resource "vault_aws_auth_backend_role"`. v1 does not carry that item. ids are
renumbered by stratum, so v0 and v1 results are not item-comparable.

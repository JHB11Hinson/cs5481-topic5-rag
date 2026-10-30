# 08: Golden QA Set v1 with a validator that can fail

**What to build:** a 60-item golden set — 40 answerable across five strata, 20 deliberate near-misses — that a validator checks before any experiment consumes it. Evidence is anchored as document plus quoted sentence, so re-chunking cannot break the set.

**Blocked by:** 02, 06.

**Status:** in-progress — v0 shipped, v1 still to draft

`golden/v0.jsonl` holds 20 items (10 answerable across fact_lookup / param_value / table_content / multi_hop / concept, 10 near-misses split into version drift, deployment-specific, sibling product, composition, procedure gap, and commercial). Validator reports 0 problems: every quote is verbatim in its document and unique in the corpus.

Quotes are never retyped. `golden/spec_v0.json` names each piece of evidence by `(doc_id, keyword)`, and `scripts/golden_emit.py` extracts the sentence or table row from the corpus. A quote that drifts from the corpus is the one defect that silently devalues every number downstream, so the pipeline makes that defect impossible rather than reviewing for it.

Remaining for v1: 40 more answerable items to meet the strata quotas in `golden/SPEC.md` (currently 3 fact_lookup / 3 param_value / 2 table_content / 1 multi_hop / 1 concept), and 10 more near-misses.

- [x] `golden/v0.jsonl` (20 items) exists before the first end-to-end run
- [ ] `golden/v1.jsonl` meets the quota table in `golden/SPEC.md`
- [x] `ragqa golden validate` implements all six checks, including quote-in-document and quote-uniqueness, and exits non-zero with a per-item report
- [x] Every quote verifies by character search after whitespace normalisation
- [x] Every item carries provenance; the count of human-edited drafts is reported with the drafting model and date
- [x] `multi_hop` items cite two distinct documents; `table_content` items resolve to a real table row

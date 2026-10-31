# 14: Baselines and swap controls

**What to build:** four comparison runs that make the system's contribution arguable — closed-book generation with no retrieval, whole-chapter long context instead of retrieval, a smaller embedding model, and a cheaper generator — each on the same 40 answerable items.

**Blocked by:** 12.

**Status:** done — five cells, one factor each where the factor is clean

- [x] Closed-book baseline uses the same generator and prompt with the retrieval block empty
- [x] Long-context baseline stuffs the full source chapter of the evidence document into the prompt and reports what the window costs and what it buys
- [x] Embedding swap to all-MiniLM-L6-v2 reports retrieval and citation metrics under the same code path
- [x] Generator swap to the cheaper model reports quality and cost shift
- [x] Every baseline is a normal run directory with an id, not a notebook experiment
- [x] The comparison table shows RAG versus no-RAG on correctness and on citation support, with paired significance

## Resolution

Four baselines plus a reference cell, all on the same forty answerable items and all
normal run directories: `runs/baseline-*`.

Closed book refuses all forty answerable questions and costs ¥0.47 per 1,000; the
whole-document long-context baseline answers all forty and is **cheaper** than the
reference cell, ¥4.24 against ¥9.10 — what it spends is the citation handle, since a
document in the prompt has no chunk to point at, and its citation precision and recall are
zero for that reason. `all-MiniLM-L6-v2` drops hit@10 from 0.90 to 0.65 at ¥7.78. The
cheap generator keeps hit@10 at 0.90 and citation precision at 0.87 for ¥4.70, a 48%
saving. `embed-minilm` moves two keys and is labelled `MULTIPLE_FACTORS(2)` rather than
pretending otherwise. Paired McNemar for each contrast is in `reports/baselines/table.md`,
computed by the same exact test the matrix table uses.

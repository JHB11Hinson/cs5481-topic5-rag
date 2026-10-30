# Topic 5 — Grounded Documentation QA

Spec for the CS5481 Topic 5 build: a RAG question-answering system over a version-pinned open-source documentation corpus, where every claim carries a verifiable citation and the system says so when the documentation does not answer.

Repo-level facts (deadline, deliverables, mandated requirements) live in `AGENTS.md`. Design decisions live in `docs/adr/`. Vocabulary lives in `GLOSSARY.md` — use its terms exactly (`Configuration`, `Golden QA Set`, `Citation`, `Span`, `Abstention`, `Sensitivity Sweep`, `Smoke Configuration`).

## What this system is

- **Corpus**: Vault 1.21.x documentation, pinned by commit (`ADR-0008`), ingested twice — once structure-aware, once as stripped plain text (`ADR-0007`).
- **Index**: Qdrant, dense + sparse, both keyed to one corpus snapshot id.
- **Retrieval**: dense / hybrid+RRF / hybrid+RRF+rerank as three levels of one factor.
- **Contextualization**: plain / contextual prefix / late chunking as three levels of another (`ADR-0006`).
- **Generation**: hosted LLM emitting structured claims with `doc_id` + `chunk_id` + `span`.
- **Verification**: programmatic span containment first, then NLI, then LLM judge, calibrated against 30 hand-labelled cases (`ADR-0004`).
- **Evaluation**: 60-item Golden QA Set, paired comparisons, McNemar + bootstrap CI (`ADR-0005`).

## Experiment inventory

34 configurations total. Every one writes an immutable `runs/<run_id>/` directory (`ADR-0003`).

| # | Experiment | Configs | Item set | Generations | Purpose |
|---|---|---|---|---|---|
| 1 | Main matrix: chunk strategy (2) × retrieval (3) × contextualization (3) | 18 | full 60 | 1,080 | headline table, main effects + interactions |
| 2 | Retrieval depth sweep k ∈ {5, 10, 20, 40} | 4 | 40 answerable | 160 | sensitivity |
| 3 | Chunk size sweep ∈ {256, 512, 1024} | 3 | 40 answerable | 120 | sensitivity |
| 4 | Agentic hops ∈ {1, 2, 3} | 3 | 40 answerable | 120 | ablation + deliberate-stop evidence |
| 5 | Embedding swap (bge-m3 → all-MiniLM-L6-v2) | 1 | 40 answerable | 40 | robustness |
| 6 | Generator swap (main model → cheap model) | 1 | 40 answerable | 40 | robustness |
| 7 | Closed-book baseline (no retrieval) | 1 | 40 answerable | 40 | necessity |
| 8 | Long-context baseline (whole chapter in prompt) | 1 | 40 answerable | 40 | necessity |
| 9 | Parse comparison (structure-aware vs stripped) | 2 | 40 answerable | 80 | parse value on this corpus |
| | **Total** | **34** | | **≈1,720** | |

Budget estimate: generation ≈¥12–20, judge ≈¥15–30, everything else free (local embedding and reranking). Ceiling ¥50. If it tightens, cut judge coverage on non-matrix cells to 50% — never shrink the Golden QA Set, which is the statistical floor.

## Metrics per configuration

- **Retrieval**: Recall@k, MRR, nDCG@10, hit rate (evidence doc present in top-k).
- **Grounding**: citation precision, citation recall, span hit rate.
- **Answer**: correctness (judge + human spot check), faithfulness.
- **Abstention**: PR curve over the score threshold, chosen working point, over-abstain rate on answerable items.
- **System**: index build minutes, index size on disk, p50/p95 latency, ¥ per 1,000 questions.

## Definition of done for the project

1. 34 configurations executed, each traceable to a `run_id` with config, git SHA, corpus snapshot, and timings.
2. 18-row matrix table with significance markers and bootstrap CIs.
3. Three sensitivity figures, judge agreement table (Cohen's kappa), error taxonomy over 40 hand-inspected failures, system cost table, two baselines.
4. Six-page report plus appendix; slides appended; contribution page last in the main report (per `AGENTS.md`).
5. `runs/` JSON committed; large artifacts excluded behind a checksummed fetch script.

## Out of scope

Graph index, ColBERT late interaction, embedding fine-tuning (`ADR-0002`), OCR/table-structure recognition (`ADR-0007`), multi-tenant auth, UI beyond a single-page demo.

## Schedule (solo, 25 days from 2026-10-30)

| Phase | Dates | Work | Exit condition |
|---|---|---|---|
| 0 | 10-31 → 11-01 | harness, corpus ingest, chunker | `smoke.yaml` produces `predictions.jsonl` + `metrics.json` |
| 1 | 11-02 → 11-04 | embed, index, retrieval, generator, golden v0 | one config answers 5 questions end to end with citations |
| 2 | 11-05 → 11-08 | contextualizer, verifier, evaluator, golden v1 (60) | 18-cell matrix runs unattended overnight |
| 3 | 11-09 → 11-13 | grid runner, curves, baselines, model swaps, error annotation | 34 configs done; failures labelled |
| 4 | 11-14 → 11-17 | aggregation, tables, figures, discussion draft | every report number traces to a `run_id` |
| 5 | 11-18 → 11-21 | report, 6 pages of main content | full draft, appendix assembled |
| 6 | 11-22 → 11-24 | slides, demo, contribution page, submission | submitted with a day of buffer |

Vertical slice first: the thinnest end-to-end path exists before any factor is expanded, so any day the work stops there is something submittable.

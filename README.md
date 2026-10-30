# CS5481 Topic 5 — Grounded Documentation QA

Question answering over a pinned documentation corpus where every claim carries a citation a program can check, and the system says so when the documentation does not answer.

Course brief: `docs/course-brief/CS5481_Project_2026-1.pdf`. Read `AGENTS.md` first for the graded constraints, `GLOSSARY.md` for the vocabulary used in every ticket and ADR, and `docs/adr/` for the decisions behind the design.

## State of the build

Tickets 01–06 are done: the real corpus, real embeddings, all three retrieval modes, and real grounded generation with programmatically verified citations. The live picture — numbers, gateway quirks, next moves — is in `docs/PROGRESS.md`.

| Piece | Status |
|---|---|
| Run contract, config schema, chunker, retrieval, containment check, metrics | done |
| Corpus ingest — Vault 1.21.x at commit `1817bdfe`, 1,268 documents | done (ticket 02) |
| Chunking — fixed window vs recursive parent-child | done (ticket 03) |
| Embeddings — bge-m3 fp16 on the 3060, sqlite cache | done (ticket 04) |
| Qdrant index, hybrid + RRF, cross-encoder rerank | done (ticket 05) |
| Grounded generation, cached, citations verified by string search | done (ticket 06) |
| Golden QA set | v0: 20 items, validated. v1: 60 items, to draft (ticket 08) |
| Contextual prefixes, late chunking, judges, curves, matrix, report | tickets 07, 09–17 |

## Measured so far

20 golden items, k = 10, identical chunks and embeddings:

| retrieval mode | hit@10 | MRR | nDCG@10 |
|---|---|---|---|
| hybrid | 1.000 | 0.759 | 0.813 |
| rerank, candidate depth 12 | 1.000 | 0.950 | 0.963 |

Index: 2,203 chunks × 1,024 dims in 22.8 MB on disk, 36 ms p50 query latency. Full embedding cache hit on re-run (2,203/2,203). Two confounds caught while measuring: a rerank run with candidate depth 8 scored 0.900 because the metric was reading a truncated list (`ADR-0011`), and the cross-encoder at its native 8,192-token length took over ten minutes and scored worse than the same model truncated to 512.

## Run it

Requires Python 3.9+ with `pyyaml` and `numpy` — nothing else for the stub path.

```bash
python -m ragqa.selftest                      # unit tests, no installs needed
python -m ragqa.run --config configs/smoke.yaml
```

The second command writes `runs/smoke-<timestamp>-<confighash>/` with twelve files: resolved config, git state, corpus snapshot, models, chunk set and stats, predictions, citations, errors, timings, cache stats, and metrics. Two runs of the same config produce byte-identical `metrics.json`.

Useful flags: `--items N` truncates the golden set, `--out DIR` redirects the run root, `--allow-dirty` permits a run on a modified tree.

## Where things live

| Path | What |
|---|---|
| `ragqa/` | pipeline modules; `run.py` is the only entry point |
| `configs/` | one YAML per experimental cell |
| `fixtures/` | tiny corpus and golden items for the stub path |
| `golden/` | field specification for the real QA set |
| `runs/` | immutable per-run evidence, one directory per configuration |
| `.scratch/topic5-rag/` | spec and the ticket board |
| `docs/adr/`, `docs/research/` | decisions ; the 13-system RAG survey |

## Conventions worth knowing before editing

- A configuration never becomes a branch. Ablations differ by YAML, and the code baseline is pinned by commit (`ADR-0003`).
- Retrieval hits are decided by locating the evidence quote in the returned chunk text, never by comparing chunk ids (`golden/SPEC.md`).
- Unimplemented stages raise. Nothing silently degrades to a simpler mode, because two cells that quietly became identical would be invisible in the results table.
- Wall-clock numbers go in `timings.json`; `metrics.json` stays deterministic.

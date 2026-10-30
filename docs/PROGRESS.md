# Progress

Where the build stands, what has been measured, and what to do next. Read this first when resuming.

## Board

| Ticket | Status | Evidence |
|---|---|---|
| 01 smoke path | done | 12-file run contract; identical `metrics.json` hash across runs |
| 02 corpus snapshot | done | Vault 1.21.x @ `1817bdfe`, 1,268 documents, 0 parse failures |
| 03 chunk strategies | done | fixed 2,318 children; recursive 2,203 children + 1,536 parents |
| 04 real embeddings | done | bge-m3 fp16 on the 3060; 2,203/2,203 cache hits on re-run |
| 05 Qdrant + retrieval | done | dense / hybrid+RRF / rerank measured on golden v0 |
| **06 grounded generation** | **done** | real answers, citations verified programmatically, ¥10 per 1k questions |
| 07 contextual prefixes | **next** | needs no new component: prefix generator + both index branches |
| 08 golden set | v0 done | 20 items validated; 60-item v1 to author |
| 09 late chunking | in progress | encoder works; documents need windowing before the full corpus |
| 10 support judges | ready | NLI layer is local; judge model is configured and reachable |
| 11 abstention curve | ready | sweep the score threshold per retrieval mode |
| 12–17 matrix, curves, baselines, demo, report | blocked on 07–11 | |

## Measured

Golden v0: 20 items (10 answerable across five strata, 10 near-misses), corpus `vault-1.21.x-1817bdfe`, chunk strategy `recursive_parent_child`, k = 10.

Retrieval, identical embeddings:

| configuration | hit@10 | MRR | nDCG@10 | wall clock |
|---|---|---|---|---|
| hybrid (dense ∥ BM25, RRF) | 1.000 | 0.759 | 0.813 | 40 s |
| rerank, depth 12, cross-encoder at 512 tokens | 1.000 | 0.950 | 0.963 | 62 s |

Generation, `deepseek-v4.1-flash`, temperature 0, rerank retrieval:

| metric | budget 900 | budget 1600 |
|---|---|---|
| citation precision | 0.941 | 0.905 |
| citation recall | 0.900 | 0.900 |
| span hit rate | 0.588 | 0.429 |
| near-misses abstained | 9/10 | 9/10 |
| over-abstention on answerable | 0.000 | 0.000 |
| claims | 17 | 21 |
| cost / ¥ per 1,000 questions | $0.030 / ¥10.0 | $0.036 / ¥12.0 |

Corpus and index: 783 pages + 485 shared fragments = 1,268 documents, 5.62 M chars (≈1.41 M tokens); 2,203 child chunks; Qdrant 21.7 MB on disk; 36 ms p50 query latency.

## Gateway facts (cost an hour to learn, do not rediscover)

- OpenCode **Go** subscription uses `https://opencode.ai/zen/go/v1` — *not* `https://opencode.ai/zen/v1`. The plain zen path is a different catalog whose upstream is unfunded and answers `402 server_error: Upstream request failed: Insufficient account funds`.
- Requests must carry an `x-opencode-session` header; the harness's own provider definition adds it (`@earendil-works/pi-ai/dist/providers/opencode-go.js`).
- Cloudflare fronts the gateway and rejects the default Python user agent; `ragqa/llm.py` sends `User-Agent: ragqa/0.1`.
- Models confirmed working: `deepseek-v4.1-flash` (cheap, used for generation), `deepseek-v4-pro` (stronger, intended judge). `python scripts/probe_models.py` lists what any key can reach.
- Credentials live in `.env` (gitignored): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_SESSION_HEADER`.

## Findings for the report

1. **Corpus sizing by guess is wrong.** ClickHouse measured 8.02 M tokens against a 1.2 M estimate; PostgreSQL 3.10 M; chosen Vault tree 1.56 M. `ADR-0008`.
2. **Shared documentation fragments duplicate.** 1,542 include references over 623 partials; inlining all copies one alert into hundreds of pages. `ADR-0009`.
3. **Heading-bounded chunking degenerates here.** Section median is 31 words, so "split on heading" yields 56–67-word chunks whatever the budget. `ADR-0010`.
4. **Candidate depth below k is a measurement trap.** Rerank at depth 8 scored 0.900 hit@10 only because ten-item recall read an eight-item list. `ADR-0011`.
5. **Cross-encoder at native length is slower and worse.** 8,192-token inputs: over ten minutes, nDCG 0.926. Truncated to 512: 62 s, nDCG 0.963.
6. **A 2,088-word table is an out-of-memory error**, not a chunk: attention is quadratic in padded batch length. Atomic units capped at 1,024 words.
7. **Temperature 0 is not determinism.** Two identical runs produced 17 and 21 claims and citation precision 0.941 versus 0.905; the response cache is what makes a run reproducible. `ADR-0012`.
8. **Hallucinated citations are real and catchable.** The verifier caught invented quotes twice, once a fabricated sentence about a `secret/` mount in a document that never mentions it — caught by string search, before any judge was consulted.

## Run it

```bash
python -m ragqa.selftest                         # 53 tests
python -m ragqa.run --config configs/smoke.yaml          # offline stub path
python -m ragqa.run --config configs/real_llm.yaml       # real generation
python scripts/inspect_run.py runs/<run_id>              # per-item failure view
python scripts/probe_models.py                           # what the key can reach
```

## Next moves, in order

1. **Ticket 07** — contextual prefixes: one cheap-model call per chunk (2,203 chunks, ¥2–5), prepend to both dense and sparse indexes, A/B against plain on golden v0, plus the 20-item prefix audit. This is one of the two mechanisms `docs/research/rag-systems-survey.md` found in no shipping open-source system.
2. **Ticket 09 windowing** — cap the late-chunking document path at ~2,048 tokens with overlap (the probe used 5.56 GB of 6.00 at 8,192), then run the three-level contextualization comparison: plain / prefix / late chunking.
3. **Ticket 10** — NLI layer is local and free; judge layer uses `deepseek-v4-pro` on the 30-item calibration sample for Cohen's kappa.
4. **Ticket 11** — abstention threshold sweep, run separately per retrieval mode (cross-encoder logits, RRF scores, and cosine live on different scales).
5. **Ticket 08 v1** — 40 more answerable items and 10 more near-misses, via `golden/spec_v0.json` + `scripts/golden_emit.py` so quotes are extracted, never retyped.
6. **Ticket 12** — the 18-cell matrix, now that every cell can actually run.

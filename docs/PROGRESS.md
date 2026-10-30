# Progress

Where the build stands, what has been measured, and what to do next. Read this first when resuming.

## Board

| Ticket | Status | Evidence |
|---|---|---|
| 01 smoke path | done | 12-file run contract, plus `artifacts.json` checksums for the two excluded files |
| 02 corpus snapshot | done | Vault 1.21.x @ `1817bdfe`, 1,268 documents, 0 parse failures |
| 03 chunk strategies | done | fixed 2,318 children; recursive 2,203 children + 1,536 parents |
| 04 real embeddings | done | bge-m3 fp16 on the 3060; 2,203/2,203 cache hits on re-run |
| 05 Qdrant + retrieval | done | dense / hybrid+RRF / rerank, ADR-0011 depth rule enforced at run start |
| 06 grounded generation | done | real answers, citations verified programmatically, ¥9–10 per 1k questions |
| 07 contextual prefixes | done | 2,203 prefixes warmed (¥0.37), 100% cache hits on re-run, 20-item audit 0% fail |
| 08 golden set | done | `golden/v1.jsonl` 60 items, strata exact, validator green |
| 09 late chunking | done | windowed at 2,048/256 tokens; window count and peak VRAM recorded per run |
| 10 support judges | done | judge kappa 0.857, NLI 0.595, label-order bug fixed |
| 11 abstention curve | done | working points per mode; hybrid ceiling shown to be a score tie |
| 12 factorial matrix | running | 18 cells emitted, checked, projection 1080/1080; cells landing now |
| 13 sensitivity + hops | configs done | 10 sweep cells emitted and dry-run-verified; curves need the runs |
| 14 baselines + swaps | done | four baseline cells + paired McNemar |
| 15 aggregate + taxonomy | done | `reports/` bundle regenerated from `runs/`, nine-class taxonomy |
| 16 demo UI | done | Chainlit, clickable citation cards, abstention case, five-question script |
| 17 report + slides | in progress | report, appendix, slides |

## Measured

### Golden v1 (60 items: 40 answerable across five strata, 20 near-misses)

First matrix cell to land, `cell-fixed-dense-plain` — fixed 512-word chunks, dense retrieval, plain chunks, `deepseek-v4.1-flash`:

| metric | value |
|---|---|
| hit@10 / MRR / nDCG@10 | 0.850 / 0.482 / 0.570 |
| citation precision / recall / span hit | 1.000 / 0.875 / 1.000 |
| over-abstain / near-misses caught | 0.100 / 20 of 20 |
| ¥ per 1,000 questions | 9.27 |

The full matrix — 18 cells, three factors — is in `reports/matrix.md` once the run finishes; every row names its `run_id`.

### Golden v0 (20 items), measured during tickets 04–06

| configuration | hit@10 | MRR | nDCG@10 | wall clock |
|---|---|---|---|---|
| hybrid (dense ∥ BM25, RRF) | 1.000 | 0.759 | 0.813 | 40 s |
| rerank, depth 12, cross-encoder at 512 tokens | 1.000 | 0.950 | 0.963 | 62 s |

Generation at the same retrieval, two token budgets: citation precision 0.941 (900) versus 0.905 (1,600), span hit rate 0.588 versus 0.429, near-misses abstained 9 of 10 either way, ¥10.0 versus ¥12.0 per 1,000 questions.

### Judges

30 hand-labelled claims: Cohen's kappa **0.857** for `deepseek-v4-pro`, **0.595** for the local NLI cross-encoder against the pre-registered 0.60 bar. The hosted judge gates reporting; NLI is a diagnostic. `notes/judge-calibration.md`.

### Contextual prefixes

2,203 prefixes for ¥0.373, p50 205 characters, 100% cache hits on re-run (0 tokens, ¥0). The 20-item audit fails nothing: `notes/prefix-audit.md`.

### Abstention working points

hybrid raw 0.030432 (precision 0.556, recall 1.000); rerank raw 0.759250 (0.714 / 1.000). Hybrid's ceiling is structural — five near-misses and two answerable items share the score 0.032522 — and `notes/abstention.md` says so rather than moving the point.

## Gateway and model facts (each cost an hour, do not rediscover)

- OpenCode **Go** subscription uses `https://opencode.ai/zen/go/v1` — *not* `https://opencode.ai/zen/v1`. The plain zen path is a different catalog whose upstream answers `402 Insufficient account funds`. `scripts/probe_models.py` probes the plain path and will always look broken; probe `$LLM_BASE_URL` directly instead.
- Requests must carry an `x-opencode-session` header, and Cloudflare rejects the default Python user agent (`ragqa/llm.py` sends `User-Agent: ragqa/0.1`).
- Both models run a **thinking channel by default**. Inside a small `max_tokens` the whole budget goes to reasoning and `message.content` comes back **empty** with `finish_reason: length` — which parses as "no claims" and looks like a model that cannot answer. `reasoning_effort: "none"` disables it, costs about a tenth, and is the right setting for mechanical calls (prefixes, query rewriting, cheap judging). Generation keeps deliberation.
- The gateway rejects `response_format: json_object` unless the prompt contains the word "json".
- **Construct models with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.** Each cell builds a fresh embedder; the hub check on `from_pretrained` can hang indefinitely at 0% GPU, which looks exactly like a deadlock. Two matrix restarts were lost to this. `scripts/run_matrix.py` sets both.
- A TLS handshake can fail mid-run. `LLMClient` retries transport errors as well as 5xx/429; without that, one bad minute of network kills a 10-minute cell.

## Run it

```bash
python -m ragqa.selftest                                   # 130+ tests, no network
python -m ragqa.run --config configs/smoke.yaml            # offline stub path
python -m ragqa golden validate golden/v1.jsonl --strict-quotas --corpus=<corpus.jsonl>
python scripts/warm_prefixes.py --config configs/ctx-prefix.yaml
python -m ragqa grid check configs/grid                    # the 18-cell declaration
python scripts/run_matrix.py                               # resumable, skips finished cells
python scripts/run_sweeps.py --runs runs --reports reports
python scripts/run_baselines.py --runs runs
python -m ragqa aggregate --runs runs --out reports        # every table and figure
python -m ragqa serve --config configs/grid/cell-recursive_parent_child-rerank-plain.yaml
python scripts/fetch_artifacts.py --runs runs              # rebuild excluded artifacts
```

## Next moves, in order

1. Finish the 18 cells, then aggregate: `python -m ragqa aggregate --runs runs --out reports`.
2. Run the ten sweep cells and regenerate the curves on golden v1.
3. Run the four baseline cells; the paired table needs the reference cell beside them.
4. Report and slides, contribution page last in the main report.
5. Re-run `sweep abstention` on the v1 runs — the committed working points were measured on v0.

## Findings worth carrying into the report

1. **Corpus sizing by guess is wrong.** ClickHouse measured 8.02 M tokens against a 1.2 M estimate; the chosen Vault tree 1.56 M. `ADR-0008`.
2. **Shared documentation fragments duplicate.** 1,542 include references over 623 partials. `ADR-0009`.
3. **Heading-bounded chunking degenerates here.** Section median 31 words. `ADR-0010`.
4. **Candidate depth below k is a measurement trap.** `ADR-0011`.
5. **Cross-encoder at native length is slower and worse.** 8,192 tokens: over ten minutes, nDCG 0.926; truncated to 512: 62 s, nDCG 0.963.
6. **A 2,088-word table is an out-of-memory error**, not a chunk. Atomic units capped at 1,024 words.
7. **Temperature 0 is not determinism.** Two identical runs produced 17 and 21 claims; the response cache is what makes a run reproducible. `ADR-0012`.
8. **Hallucinated citations are real and catchable** by string search before any judge is consulted.
9. **A model's label order is part of the model.** The NLI layer read `[contradiction, neutral, entailment]` on a checkpoint that is `[entailment, neutral, contradiction]`, and every verdict it produced was inverted until calibration caught it.
10. **A reasoning budget can silently eat the answer.** See the gateway facts above.
11. **Score scales are per retrieval mode.** One abstention threshold across hybrid and rerank abstains on everything in one and nothing in the other; the RRF lattice also ties five near-misses with two answerable items at exactly 0.032522.

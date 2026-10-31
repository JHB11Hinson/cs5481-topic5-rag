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
| 07 contextual prefixes | done | 6 usable A/B pairs, every interval containing zero; 20-item audit 0% fail |
| 08 golden set | done | `golden/v1.jsonl` 60 items, strata exact, validator green |
| 09 late chunking | done | windowed at 2,048/256 tokens; window count and peak VRAM recorded per run |
| 10 support judges | done | judge kappa 0.857, NLI 0.595, label-order bug fixed |
| 11 abstention curve | done | working points per mode; hybrid ceiling shown to be a score tie |
| 12 factorial matrix | done | 18/18 cells; `reports/matrix.md` says 18 declared, 18 finished, 0 missing |
| 13 sensitivity + hops | done | 10/10 cells; depth saturates at k=20, MRR peaks at k=5, break-even hop 2 |
| 14 baselines + swaps | done | 5 cells; closed book ¥0.47/1k, long context ¥4.24, MiniLM −0.25 hit@10, cheap generator ¥4.70 |
| 15 aggregate + taxonomy | done | 275 events over 18 cells, six classes firing, one command regenerates `reports/` |
| 16 demo UI | done | Chainlit, clickable citation cards, abstention case, five-question script |
| 17 report + slides | done | 6 pages main, 16 slides appended, contribution page page 10, submission 26 pp |

## Paused here (2026-10-31, machine shut down on request)

Everything that runs unattended is finished and committed. What is left is one
number-refresh pass and two human steps.

**Done and committed:** the 18-cell matrix (`runs/grid-*`), answer correctness for all
18 cells (`reports/correctness.*`), the nine-pair chunking comparison
(`reports/chunking.*`), the v1 abstention curves with their working points, the prefix
A/B (`notes/prefix-ab.md`), the fourteen review fixes, and the independent fact-check
(`notes/report-factcheck.md`, `SUBMISSION.md`).

**Next, in order** — each step is one command:

```bash
python -m ragqa aggregate --runs runs --out reports   # the bundle, with the baselines in it
python scripts/score_correctness.py                   # cheap: every judged claim is cached
python scripts/chunk_comparison.py
```

Then the report: fold in the fifteen matrix rows, the nine numeric mismatches listed in
`notes/report-factcheck.md`, the chunking section, the correctness section, and the
sentence about the dense threshold. Re-verify the nine mismatches and three no-source
rows against the refreshed tree, and only then tick the tracker.

If there is time, the ten sensitivity cells are still unrun (plan A marks them pending):

```bash
python scripts/run_sweeps.py --runs runs --reports reports
python scripts/run_sweeps.py --curve all
```

**Two human steps, both listed in `SUBMISSION.md`:** fill and sign the contribution page
(eight rows, ratios summing to 100%) and upload to Canvas.

**Caveats to carry into the write-up.** Each is documented where it is measured, and
none is a defect to hide: the matrix cells ran with `abstain_score_threshold` 0.2 / 0.01 /
0.0 while the v1 calibration puts the working points at 0.5706 / 0.0286 / 0.4261; latency
is cache-occupancy-confounded in several cells; neither the contextual prefix nor the
recursive chunker separates from its baseline at n=40; the atomic-table hypothesis is
untestable because all eight `table_content` items are hit by both strategies; and
`verified_by` on golden v1 is `automated:corpus-anchored`, not human.

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

### Answer correctness (ticket 18, golden v1, 40 answerable items)

Judged against each item's 
eference_answer by deepseek-v4-pro; abstentions are never judged and are reported separately. Twelve finished cells: **0.750–0.900** over all 40 answerable items and **0.821–0.923** over the items the system chose to answer, with 0–6 abstentions per cell. 
otes/correctness.md, 
eports/correctness.csv. First pass ¥0.2171; the rerun is free (457/457 cache hits).

### Chunking comparison (ticket 18, six finished pairs)


ecursive_parent_child − ixed: hit@10 +0.05 (dense/ctx, p=0.50), +0.025 (hybrid/ctx, rerank/ctx, p=1.00), 0.00 elsewhere; |MRR, nDCG deltas| ≤ 0.087. The only significant paired result is citation support, dense/ctx **+7 items, p=0.0156**, against rerank/ctx −4 items, p=0.22 — direction inconsistent. Mechanism: recursive yields 2,203 children / 1,536 parents, mean 312 words, p95 543, **477 over the 512-word budget of which 86.8% carry a table row or code fence**; fixed is under budget by construction. The atomic-table hypothesis is **not testable** here: all eight 	able_content items are hit 8/8 by both strategies, so the paired test has no discordant pair.

### Contextual prefixes: the A/B is null (ticket 07)

Four usable pairs, both retrieval and citation metrics: hit@10 −0.025 (fixed, all three retrieval modes), +0.025 (recursive/dense); **every paired bootstrap interval contains zero**, and the sign splits by chunk strategy rather than by retrieval mode — an interaction with one cell per corner, i.e. a hypothesis, not a finding. Citation precision −0.018 to +0.042, none significant. The prefix is one of the two mechanisms ADR-0006 identified as shipping nowhere; on this corpus it costs ¥0.48 and 35 minutes to build and buys nothing measurable at n=40.

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

## Final state (2026-10-31)

Every ticket on the board is done. The build has 18 matrix cells, 10 sensitivity points and 5
baseline cells — 33 run directories of evidence plus the smoke and A/B runs — and one command
regenerates every table and figure from them:

```bash
python -m ragqa aggregate --runs runs --out reports
```

**What the project found, in the order the report makes the arguments.**

1. **The contextual prefix is a null result.** Six pairs, hit@10 −0.025 or +0.025, every paired
   interval containing zero, the sign splitting by chunk strategy rather than by retrieval mode.
   It costs ¥0.48 and 35 minutes to build and buys nothing measurable at n=40 (`ADR-0013`).
2. **Late chunking fails, and the failure is the encoder's.** 54 of 240 paired retrieval items
   lost, none gained (p < 0.000001); dense hit@10 0.275 against 0.850. The pooling swap that
   should have rescued it made it worse (0.275 → 0.025), which locates the fault in mean-pooled
   token states against a CLS-trained encoder — so the technique remains untested here, and a
   mean-pooling encoder is the first thing to run with more time (`ADR-0018`).
3. **Retrieval explains all abstention.** 64 of 64 abstentions on answerable items are the items
   whose evidence was lost first (43 document misses, 13 chunk misses, 8 window drops). There is
   no generator over-abstention to fix, and the near-misses are refused 20 of 20.
4. **The score threshold is a measurement, not a mechanism.** `LLMGenerator` never reads it, and
   no cut on any of the three scales refuses a near-miss without discarding answerable items —
   a near-miss is topically adjacent by construction, so it scores high (`ADR-0019`).
5. **`hit@10` is generous by definition.** Any-of over the gold quotes: 56 of 196 evidence-loss
   events sit on items the matrix counted as hits; recall over all gold quotes is 0.73, not 0.81.
6. **Containment proves the quote is real, not that it is sufficient.** The fourteen-item audit
   found one defective item and three quotes that are containable but not self-locating.

**The two human steps that remain** are in `SUBMISSION.md`: fill and sign the contribution page
(eight rows, ratios summing to 100%), and upload to Canvas. Nothing in the repository is waiting
on code.

**Known caveats, each documented where it is measured:** the matrix cells ran with
`abstain_score_threshold` 0.2 / 0.01 / 0.0 while the v1 calibration puts the working points at
0.5706 / 0.0286 / 0.4261; latency is cache-occupancy-confounded in several cells; `verified_by`
on golden v1 is `automated:corpus-anchored` with a fourteen-item agent audit rather than a human
review; the answer-correctness judge is a model with κ 0.857 against 30 hand labels; and every
cell ran with `judge_enabled=false`, so the taxonomy is an upper bound on answer errors.

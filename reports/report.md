# A Documentation Knowledge Base That Cites What It Says, and Says Nothing When It Cannot

**CS5481 Data Engineering — Group Project, Topic 5 · 24 November 2026**

Knowledge base: Vault 1.21.x documentation, snapshot `vault-1.21.x-1817bdfe` (1,268 documents, 5.62 M characters, commit-pinned). Code: `ragqa/` (Python); demo: one Chainlit screen. Every number below names a `runs/<run_id>/` directory or a row of the generated `reports/` bundle; §A.2 indexes the artifacts.

## 1 Introduction

The brief asks for question answering over a private document set in which every claim is tied to a retrieved source and a missing answer is stated instead of invented. This report is about the engineering half of that problem: how a chunk is formed, contextualised and narrowed, and how a citation is *checked* rather than believed. Our answer to the last question is a three-layer verifier whose first layer is arithmetic — a claim must quote text that occurs inside the chunk it cites (ADR-0004) — and our answer to the first three is an 18-cell factorial matrix over chunk strategy, retrieval mode and contextualisation, measured against a 60-item Golden QA Set.

On that set, the hybrid configuration with fixed chunks and no contextualisation returned the evidence chunk inside the top 10 for **90.0% of the 40 answerable questions** (95% bootstrap CI 80.0–97.5) and carried a citation whose quoted span occurs in the cited chunk for **95.0%** of them, while abstaining on **20 of 20** deliberately unanswerable near-misses, at **¥8.46 per 1,000 questions** — run `grid-fixed-hybrid-plain-20261030T125429-6170ae66`. The same pipeline with dense retrieval scores 85.0% (72.5–95.0) hit@10 and 87.5% citation recall at ¥9.27 per 1,000 — run `grid-fixed-dense-plain-20261030T124637-8ae4eb06`.

That pair is the whole of our measured matrix. **Two of the eighteen cells have finished runs; the other sixteen are `missing` in `reports/matrix.md` and are reported here as missing.** We do not interpolate, and no sentence below rests on a number a run directory does not carry. We can therefore describe a design, one contrast, one operating point, one verifier calibration and fourteen diagnosed failures, and we cannot yet attribute an effect to chunk strategy or to contextualisation.

Contributions, in the order the experiments support them: a **citation contract checked in code before it is judged by a model** (structured claims carrying `doc_id`, `chunk_id` and a span; containment, then NLI, then a judge calibrated on 30 hand labels, §3.4); an **18-cell design with paired tests and intervals fixed before the runs** (ADR-0005), whose generator prints `missing` rather than a guess; a **calibrated abstention path** — an 18-point precision-recall sweep per retrieval mode with the working-point rule fixed in advance, and the raw threshold written back per mode because the three modes do not share a score scale (§3.2); an **error taxonomy of nine classes** assigned by the earliest layer that lost the answer, which is what §4 argues from rather than from the metric table; and a **cost accounting that refuses the obvious argument**, because long context is not the expensive baseline on this corpus (§3.6).

The brief's five requirements map one-to-one: data preparation and the chunking comparison (§2.1, §3.3), storage (§2.2), retrieval (§2.2), grounded generation with per-claim citation and explicit abstention (§2.4, §3.2), and evaluation over a test set of at least 20 pairs — ours has 60 (§2.5, §3.1).

## 2 Methodology

### 2.1 Corpus, parsing and chunking

The knowledge base is the Vault documentation at `content/vault/v1.21.x` in `hashicorp/web-unified-docs`, pinned by commit SHA (ADR-0008) and ingested by blobless sparse checkout. It is parsed twice — structure-aware and stripped plain text (ADR-0007) — leaving 1,268 documents, 5,622,957 characters, median 1,573 and mean 4,434.5 (`reports/baselines/window-cost.json`). Chunking is a two-level factor. **Fixed** cuts word windows with overlap. **Recursive parent-child** accumulates units (sentence, table, fenced code block) to a child budget, records the heading path of the unit starting each chunk, and groups consecutive children into a 2× parent, keeping tables and code blocks atomic (ADR-0010). Heading-bounded splitting was rejected on measurement: 9,444 sections across 1,268 documents with a median of 31 words gave children sized by heading density (mean 56–67 words at a 128, 192 or 256-word target) and parents indistinguishable from children. `fixed` yields 2,318 chunks and a 22.9 MiB index; `recursive_parent_child` yields 2,203. Shared include fragments referenced by several pages are indexed once, with the referring page keeping a `[shared partial: …]` marker, so one alert box cannot become hundreds of near-identical chunks (ADR-0009).

### 2.2 Storage, retrieval levels and contextualisation levels

Chunks and embeddings live in Qdrant, dense and sparse, keyed to one corpus snapshot. Embedding and reranking are local (`BAAI/bge-m3`, 1,024 dimensions, 8,192-token window; `bge-reranker-v2-m3`); only generation and judging are hosted (ADR-0001). Retrieval has three levels — **dense**, **hybrid** (dense + BM25 fused by reciprocal rank fusion), and **hybrid + cross-encoder rerank** — at `k=10`, and every level keeps at least `k` candidates after its last stage (`rerank_top = max(k, 12)`), because a stage returning 8 candidates while the metric counts 10 measures truncation, not retrieval (ADR-0011). Contextualisation has three levels: **plain**; a **contextual prefix**, one generated sentence situating the chunk in its document, prepended before embedding and audited against a four-criterion rubric on 20 of the 2,203 cached prefixes; and **late chunking**, which encodes each document in 2,048-token windows with 256 overlap and pools each chunk's vector from the token states covering its span (ADR-0015) — the whole-document variant peaked at 5.56 GB of a 6.00 GB card, which is why the window exists. The prefix is used on the index side only and never shown to the generator (ADR-0013): if the model could quote it, a correct answer would be recorded as a containment failure, since the prefix exists nowhere in the chunk.

### 2.3 Grounded generation and the citation contract

The generator returns JSON: an `answerable` flag and claims carrying `text`, `doc_id`, `chunk_id`, `span_start`, `span_end` and a verbatim `quote`. **Containment** is arithmetic — the quote must occur in the cited chunk and the offsets must delimit it — and only claims that survive reach the **NLI cross-encoder** (`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`) and the **hosted judge** (`deepseek-v4-pro`). Abstention is explicit: a statement that the knowledge base does not answer, with the best-scoring chunk shown beside it. The generator receives the retrieved child, not its parent (ADR-0017): a 1,024-word parent with a 60-word citation would fail containment on parent-only text, and the failure rate would measure bookkeeping rather than the model. `retrieved[].parent_id` is carried through so the parent can be used later without re-indexing.

### 2.4 The 18-cell design, the golden set and the statistics

The matrix is chunk strategy (2) × retrieval mode (3) × contextualisation (3) = 18 cells, each a configuration file run by one code baseline at one pinned commit and each writing an immutable `runs/<run_id>/` (ADR-0003); cells are joined to runs by a config digest recomputed from the cell's YAML, never by timestamp. The **60-item Golden QA Set** (ADR-0005) is identical for every cell:

| Stratum | Items | Difficulty |
|---|---|---|
| `fact_lookup` (A001–A010) | 10 | easy 4, medium 6 |
| `param_value` (A011–A018) | 8 | easy 2, medium 6 |
| `table_content` (A019–A026) | 8 | medium 5, hard 3 |
| `multi_hop` (A027–A034) | 8 | hard 8 |
| `concept` (A035–A040) | 6 | medium 6 |
| **answerable** | **40** | easy 6, medium 23, hard 11 |
| `near_miss` (U001–U020) | 20 | easy 4, medium 11, hard 5 |
| **total** | **60** | easy 10, medium 33, hard 17 |

Evidence is anchored as `(doc_id, quoted sentence)` rather than a chunk id, so re-chunking cannot break the set. The 20 near-misses come from five generators — a later release than the snapshot, deployment-specific state, a sibling product's documentation, an undocumented combination of two documented features, and commercial-only facts — each verified to occur zero times in the corpus, and each naming a `near_miss_doc` that does exist so the metadata does not leak the answer. Comparisons are paired by item: McNemar's exact test (two-sided) on discordant pairs, and 10,000-resample percentile bootstrap intervals whose resample unit is the *item*, not the claim (seed `20261030` mixed with the cell name). Twenty items was the original plan and was too small on both counts: 20 negatives give a 21-point abstention curve rather than a staircase, and at a 0.75-versus-0.90 difference 60 answerable items yield about 12 discordant pairs (10:2, p≈0.04) where 24 yield about 5 (p≈0.38). Set size, not cell count, decides whether any claim here can carry a significance marker.

### 2.5 What we deliberately did not build

| Omitted | Why |
|---|---|
| Graph index (GraphRAG / LightRAG style) | An entity-relation extraction pass plus community summarisation over every chunk, paying off only on cross-document multi-hop — a question type one product's manual barely produces (ADR-0002). |
| ColBERT-style late interaction | Multiplies index size per token and complicates the storage story, for a gain our two stage-2 rankers already chase (ADR-0002). |
| Embedding fine-tuning | Needs labelled pairs we do not have, and would make the chunking and retrieval cells harder to attribute (ADR-0002). |
| OCR / table-structure recognition | The source is markdown and MDX: tables arrive as pipe tables, code as fenced text. Layout analysis recovers structure this corpus never lost; what structure is worth is measured instead, by parsing twice (ADR-0007). |
| Multi-tenant auth; a UI beyond one screen | The brief's challenge is the backend pipeline; one screen showing citations and abstention is what a demo has to show. |
| Prefix inside the generation prompt | Would break containment and confound the contextualisation factor with a prompt change (ADR-0013). |
| Whole-document late-chunking windows | 5.56 GB of a 6.00 GB card, and a 53 k-character document truncated at the window — the exact failure late chunking exists to prevent (ADR-0015). |

## 3 Experiments

### 3.1 The matrix, and the intervals it cannot yet support

Eighteen cells are declared, two have finished runs, one has a run directory with no `metrics.json` (printed as unfinished, not as a result), and fifteen have produced nothing; `reports/matrix.json` records zero digest drift, zero orphan runs and zero unreadable ones.

| chunk | retrieval | context | hit@10 | MRR | cit. rec. | ¥/1k | run id (digest) |
|---|---|---|---|---|---|---|---|
| fixed | dense | plain | 0.8500 | 0.4817 | 0.8750 | 9.2745 | `…8ae4eb06` |
| fixed | hybrid | plain | 0.9000 | 0.6529 | 0.9500 | 8.4638 | `…6170ae66` |
| fixed | rerank | plain | — | — | — | — | unfinished |
| fixed | any | contextual_prefix, late_chunking (6 cells) | — | — | — | — | not yet measured |
| recursive_parent_child | any | any (9 cells) | — | — | — | — | not yet measured |

Main effects over the cells that exist, each mean carrying its cell count because a level resting on one cell is not the same claim as one resting on six: chunk `fixed` 0.8750 hit@10 over 2 cells and `recursive_parent_child` unestimated; retrieval `dense` 0.8500 over 1, `hybrid` 0.9000 over 1, `rerank` unestimated; contextualisation `plain` 0.8750 over 2, the other two unestimated. Every interaction term in `reports/matrix.md` is zero **by construction** — an interaction needs four corners of a 2×2 sub-table and two exist — and the file says so rather than letting the zeros read as evidence of additivity. All nine factor contrasts in `reports/significance.md` print `missing` for the same reason.

![](assets/report/fig1-intervals.png)

*Figure 1 — point estimates and 95% bootstrap intervals for the two finished cells (10,000 resamples, unit = item). Source: `reports/significance.csv`; runs `grid-fixed-dense-plain-20261030T124637-8ae4eb06`, `grid-fixed-hybrid-plain-20261030T125429-6170ae66`.*

Figure 1 puts the one real contrast next to its uncertainty. Hybrid leads dense by 5.0 points of hit@10, 17.1 of MRR and 7.5 of citation recall, and every interval overlaps; with no second end of any contrast there is no discordant-pair table to test. **This is a direction, not a result.**

### 3.2 Abstention as a calibrated decision

Each item's top retrieval score is swept over an 18-point grid on [0.2, 0.9]; a positive is an answerable item that should be answered, a negative a near-miss that should be refused. The three modes do not share a scale — cosine, an RRF fused sum around 1/(60+rank), a cross-encoder score in [0, 1] — and one number across them is visibly destructive: the shipped hybrid threshold of 0.20 abstained on all 20 items of its run because the RRF scale never reaches 0.20. So the sweep runs in a normalised space (z-score then standard-normal CDF for hybrid, rerank and llm; identity for cosine) and reports each point's raw equivalent, the only value that can be written back into a configuration. The working-point rule was fixed first: maximise F1 of the answer class subject to over-abstention on answerable items ≤ 0.05, ties to the larger threshold.

| mode | t (normalised) | raw threshold | precision | recall | over-abstain | under-abstain |
|---|---|---|---|---|---|---|
| hybrid | 0.4059 | 0.030432 | 0.556 | 1.000 | 0.000 | 0.800 |
| rerank | 0.4471 | 0.759250 | 0.714 | 1.000 | 0.000 | 0.400 |
| llm | 0.4471 | 0.759250 | 0.714 | 1.000 | 0.000 | 0.400 |

Source: `reports/abstention/working-points.json`, fitted on `real-hybrid-*`, `real-rerank-*` and `real-llm-*` over golden v0 (20 items, 10 answerable).

![](assets/report/fig2-abstention.png)

*Figure 2 — abstention precision-recall curves with the chosen working point per mode. Source: `reports/abstention/{rerank,hybrid}-pr.csv`; runs `real-rerank-20261030T095541-a6eb2d5e`, `real-hybrid-20261030T092148-08d22872`.*

Figure 2 shows why the modes behave differently. Rerank is the staircase a calibrated score gives; hybrid is a plateau then a cliff — two answerable items and five near-misses all score exactly 0.032522 while five answerable items score 0.032787, a gap of 0.000265 on a scale spanning 0.0164–0.0328. An RRF sum takes a handful of lattice values and is symmetric in the two classes: an unanswerable question both branches rank first is indistinguishable from a real one by this score. Precision collapses there structurally, which is why the reranked and model-judged paths are the ones we adopt and a rank-fusion score is never treated as a confidence. Two limits belong beside the table. **The tuned threshold never fires inside the matrix**: it travels with the retrieval level (0.20 dense, 0.01 hybrid) while the items that abstained scored 0.658 and 0.032 — far above their thresholds — so all 24 abstentions in the dense cell and all 22 in the hybrid cell carry a written `abstain_reason` and the abstention columns measure the generator, not the calibrated operating point. And the working point is fitted on v0's ten positives and ten negatives, so every rate moves in steps of 0.1 and a 0.05 budget is arithmetically zero: a starting point, not a measurement.

### 3.3 The three sensitivity curves

Three one-parameter families are declared around one reference cell (`configs/grid/cell-recursive_parent_child-rerank-plain.yaml`), so a difference between two points is attributable to the swept key alone; every point holds the same 40 answerable items, corpus, embedder, truncation and prices, and `sweeps.check` refuses a cell that differs outside its own parameter.

| Curve | Swept key | Points | Items/point | Generation calls | Status |
|---|---|---|---|---|---|
| depth | `retrieval.k` | 5, 10, 20, 40 | 40 | 160 | 0 of 4 finished |
| chunk size | `chunk.size` | 256, 512, 1024 | 40 | 120 | 0 of 3 finished |
| hops | `retrieval.hops` | 1, 2, 3 | 40 | 120 | 0 of 3 finished |

**All ten points are pending: no curve is reported as a curve.** `reports/sweeps/{k,chunk,hops}.{md,csv}` carry the declaration with every metric marked pending, and the three `reports/figures/sweep-*.png` files are placeholders that say so. What is fixed in advance is the expected shape and the rule that will read it: depth should rise while the retriever still misses evidence a wider net could reach, then flatten once the misses are misses at any depth; chunk size should show citation precision peaking before citation recall does, with the 1,024-word point read as a lower bound because `embed.max_seq_length` is 1,024 tokens and a 1,024-word child exceeds it; hops should show the second round recovering what the first put below the trigger (`retrieval.trigger_threshold = 0.5771`, the raw score at t = 0.2, deliberately 0.182 below the 0.75925 abstention point so a round already answered is never rewritten) and the third recovering little while still paying a rewrite call of at most 200 output tokens. The break-even rule is pre-registered: the loop stops paying at the first hop whose marginal ¥ per recall point is at least the previous hop's, or whose recall gain is zero — and "the loop never fires" is a result that returns hop 1 at about ¥1.00 per 1,000 questions. This is also where the brief's chunking comparison would be settled most cleanly: the size curve isolates size, the matrix's `fixed` versus `recursive_parent_child` contrast isolates boundary criteria, and neither half has a measured number yet.

### 3.4 Judge agreement

Thirty claims — twenty verbatim from real generation runs, ten controlled negatives built by one documented edit to a verbatim claim (a value flipped, a negation dropped, a relation reversed, a default borrowed from a neighbouring option, a path swapped) — were labelled by hand against the full cited chunk. The bar, κ ≥ 0.60, was fixed before any judge ran.

| Layer | n | agreement | precision | recall | κ | role |
|---|---|---|---|---|---|---|
| containment (string) | 30 | 0.667 | 0.667 | 1.000 | 0.000 | advisory |
| NLI cross-encoder | 30 | 0.833 | 0.826 | 0.950 | 0.595 | advisory |
| hosted judge (`deepseek-v4-pro`) | 30 | 0.933 | 1.000 | 0.900 | 0.857 | **gates reporting** |

Source: `reports/judges.md`, recomputed from stored verdicts against `notes/judge-calibration.json`. The judge clears the bar with no false-positive call in 30 rows; its two misses are false negatives on true claims (a chain compression, and a sentence at the very end of a long chunk), the honest description of a conservative layer. The NLI layer misses at 0.595, and the decision does not rest on that 0.005 — with 30 rows the standard error of κ is about ±0.18, so 0.595 and 0.60 are one number measured once. It rests on direction: five claims are `nli_only` and none is `judge_only`, so every disagreement inflates support, and a layer whose only errors push the headline number up cannot gate it. Because the conjunction in `SupportJudges.judge_claim` is therefore identical to the judge's own verdict here, the NLI layer is a free local screen that can only cost recall. **No matrix cell ran with the judge enabled**, so §3.1's citation columns are containment numbers — "the quoted span occurs in the cited chunk", not "the citation supports the claim" — and any faithfulness claim needs the judge-enabled headline cells.

### 3.5 The error distribution

Fourteen failures were hand-assigned across the two finished cells, from 18 candidates, after an abstention caused by a retrieval miss was counted as that miss's symptom rather than as a second failure. The nine classes were fixed before the runs were inspected, and each failure is assigned to the earliest layer that lost the answer.

| Class | dense / plain | hybrid / plain | Total |
|---|---|---|---|
| `retrieval-document-miss` | 4 | 2 | 6 |
| `retrieval-chunk-miss` | 2 | 2 | 4 |
| `generator-over-abstention` | 1 | 1 | 2 |
| `citation-quote-not-in-chunk` | 0 | 1 | 1 |
| `generation-parse-failure` | 1 | 0 | 1 |
| four classes with no instance (`context-budget-drop`, `generator-under-abstention`, `citation-span-out-of-bounds`, `citation-chunk-not-retrieved`) | 0 | 0 | 0 |
| **total** | **8** | **6** | **14** |

Source: `notes/error-taxonomy.md`, rows assigned by reading the claim, the cited chunk and the retrieved list in `grid-fixed-dense-plain-20261030T124637-8ae4eb06` and `grid-fixed-hybrid-plain-20261030T125429-6170ae66`; drawn in Figure 3. The ticket's target was 40 hand-inspected failures; 14 is what two cells contain at roughly 6–9 failures per cell, and the shortfall is reported rather than padded.

![](assets/report/fig3-error-classes.png)

*Figure 3 — hand-assigned failures per class, per finished cell. Source: `notes/error-taxonomy.md`; the two runs above.*

### 3.6 Baselines, and the cost argument we cannot make

Four comparison cells are configured — closed book, long context, a smaller embedder (`all-MiniLM-L6-v2`, 384 dimensions and 256 positions, with dense retrieval so the cross-encoder cannot repair the stage being measured), and a cheaper generator — each differing from the reference in exactly one declared factor, checked by `ragqa.baselines.substantive_diff`. **None has a completed run**, so `reports/baselines/table.{md,json}` is deliberately absent: a table with no runs in it would misrepresent what was measured.

![](assets/report/fig4-prompt-shape-cost.png)

*Figure 4 — projected CNY per 1,000 questions by prompt shape, with mean prompt tokens. Source: `reports/baselines/window-cost.json`, built from `real-llm-20261030T113604-a5c0a3e4` and the corpus snapshot.*

What *is* measured is the prompt shape each cell would use, and it settles one question already. Priced at `deepseek-v4.1-flash`'s $0.15/$0.60 per million tokens on the 20 golden v0 items, **long context is the cheaper baseline, not the expensive one**: a 20,000-character document cap costs ¥4.77 per 1,000 questions against the reference cell's ¥9.54, and even the no-truncation 70,000-character row is ¥5.28. The reason is structural — this corpus's documents are short (mean 4,435 characters) while the reference prompt pastes eight chunks at once, 6,897 prompt tokens against 2,131. The projections reproduce the measured RAG prompt to within 8% (6,897 projected against 7,479 measured), and an 8% error bar cannot close a 3× gap. So we do not run the "long context is too expensive" argument; what long context costs is the **citation handle**. Its prompt contains no chunk ids — there are none to contain — so a claim comes back citing a document id, `verify.check_claims` does not find it among the retrieved chunks, and the claim is filed as `chunk_not_retrieved`. The generator swap was probed rather than guessed: nineteen requests across twelve models, each a miniature of this project's own task (same system prompt, one chunk, same JSON contract, `max_tokens: 900`), scored on whether the contract parsed and the quote returned verbatim, total spend $0.0017 (`reports/baselines/generator-probe.json`). `gpt-6-luna` won at $0.001019 per question against $0.001430 — ¥6.80 against ¥9.54 per 1,000, a 29% saving, a reasonable business claim and not a headline.

### 3.7 System cost

| Cell | generator | tokens in | tokens out | ¥ total | ¥/1k | index | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| dense / plain (`…8ae4eb06`) | deepseek-v4.1-flash | 415,147 | 35,261 | 0.5565 | 9.2745 | 22.9 MiB | 17.3 | 21.3 |
| hybrid / plain (`…6170ae66`) | deepseek-v4.1-flash | 387,766 | 29,952 | 0.5078 | 8.4638 | 22.9 MiB | 39.9 | 7,502.5 |

Source: `reports/cost.md`. Embedding and reranking are local, so their cost is electricity rather than a line item; the money is tokens. Beside it: the prefix warm-up over 2,203 chunks cost ¥0.373, the rerun with the cache warm cost ¥0.000 with 2,203 hits and identical strings — which is what makes that A/B a comparison rather than two samples — and the judge calibration cost ¥0.0436 for 30 calls, about ¥0.15 per 1,000 claims. **The latency columns do not measure serving latency.** The dense cell served 61 of its 64 LLM calls from the response cache and the hybrid cell 36 of 60, so a 17.3 ms p50 is a SQLite read rather than a network round trip and the hybrid cell's 7,502.5 ms p95 is one uncached item. Read down the column and it ranks cells by cache luck; a cold-latency table needs cacheless runs.

### 3.8 Threats to validity

- **Two cells.** Main effects rest on one or two cells per level, interactions and all nine paired contrasts are unestimated, and the sixteen missing cells are the largest open item in this report.
- **Golden v1 was not read by a human.** `verified_by` is `automated:corpus-anchored` on all 60 items: every quote was proven to appear verbatim and exactly once in the corpus, and every question was written from a sentence read in its document context. Nobody opened the items against the documents, so the set is verified as *text*, not as grading behaviour.
- **Citation numbers are containment, not support** (§3.4), and **abstention in the matrix is the generator's, not the threshold's**, on a working point fitted to ten positives (§3.2).
- **Latency is cache-dominated and cost is one run's recorded USD scaled up** (§3.7), not a billing statement.
- **The closed-book baseline is uninformative by construction**: the system prompt instructs the model to answer only from the provided chunks and to set `answerable: false` otherwise, so with the block emptied a compliant model declines. It bounds what the context block buys under this prompt; it says nothing about what the model knows.
- **Error counts are 14, not 40**, and the classes with no instance are listed because a class list containing only what happened cannot say what was looked for and absent. `context-budget-drop` can only appear when a hit lands at rank 9 or 10, since `retrieval.k` is 10 and `llm.context_chunks` is 8; if it stays empty across eighteen cells, the honest conclusion is that the narrowing never bites.

## 4 Discussion

The metric table says hybrid beats dense by five points of hit@10. The taxonomy says something more useful: **ten of the fourteen failures are retrieval failures, and they are two different failures.** Six are document misses, where no chunk of the evidence document reached the returned depth. Four are chunk misses, where the right document arrived and the passage did not. Everything else — two generator over-abstentions, one fabricated span, one parse failure — is five failures total, and no retrieval tuning touches them.

The distinction makes the next experiment decidable. **Chunk misses are the class contextualisation is designed to move**, and the taxonomy names the mechanism item by item. A010 and A030 fail the same way in both cells: `docs/enterprise/replication` arrives at ranks 1 and 6 in the dense cell and `docs/concepts/mount-migration` at rank 8 in the hybrid cell, yet neither returned chunk contains the quoted sentence, because the failover paragraph sits in a sibling chunk of the same page. A015 is the sharpest instance and changes class between cells: with dense retrieval the quote-bearing chunk *was* in context and the generator refused anyway (over-abstention), while with hybrid fusion the cache-table row was split into a neighbouring chunk (chunk miss). That is one item moving from "the reader was too strict" to "the index put the answer next door", which is exactly the delta a contextual prefix or a late-chunked vector should produce. The prefix audit says the mechanism is sound here — 20 of 20 sampled prefixes passed a four-criterion rubric, 0% against a 20% failure bar — so the cells are worth running rather than the mechanism being worth doubting.

**Document misses are a different disease with a different cure.** A035 fails identically in both cells: `docs/concepts/seal` is never retrieved and three of the returned documents are overview pages whose prose restates the question without the mechanism. A038 fails because an overview page's paraphrase of the golden quote satisfies the surface match while being unable to support the "why". A016 shows the lexical half: an option name with an underscore behaves like an opaque token and the parent page is never reached. No chunk-boundary mechanism fixes these; a reranked candidate list, a document-level second hop, or a graph edge from "this overview page points at that mechanism page" would. This is the one place the omitted graph index (ADR-0002) would plausibly pay, and the taxonomy supplies the condition under which to revisit it: not "multi-hop questions are interesting" but "six of fourteen failures are document misses on pages the corpus cross-references". ADR-0002's revisit clause was exactly that test, so the honest reading is that the test has been met at a small scale and should be re-run at eighteen cells before anything is built.

The five non-retrieval failures argue for two cheap fixes and one boundary. A031's dense-cell failure is a parse failure: the model produced the right fact and the contract layer could not read the envelope — a generation-format bug, not a grounding one, recorded as its own class precisely so it cannot be averaged into a faithfulness number. A015's dense-cell over-abstention is a heading-join problem, the chunk stating the default as a bare `131072` under a heading the model did not connect to "storage read cache"; A031's hybrid-cell over-abstention is a two-passage join. Both are the parent-chunk question ADR-0017 left open: `retrieved[].parent_id` already travels through retrieval, so handing the generator the 1,024-word parent while citing the 60-word child needs a second span field rather than a re-index, and that is the cheapest experiment on the list. A032 is the boundary: one claim quoted a sentence that lives in a document nobody retrieved, with span `-1`. One fabricated citation out of 47 containment-checked claims is the measured rate of span-level invention in this pipeline, and it is why containment runs before any judge — a judge would have had to notice; a string comparison simply refuses.

Two observations cut against our own numbers. The hybrid cell's abstention looks ideal — 20 of 20 near-misses refused, 2 of 40 answerable items refused — but neither figure is the threshold's work: it sat at 0.01 while every observed score cleared it, so both were the generator's judgement, and the calibrated point that would have refused 8 of those 10 near-misses (§3.2) was never in force. And the dense cell's citation precision is a perfect 1.000 over 35 claims, which is a property of a strict generator that emitted nothing rather than a fabrication when it lacked support; its 10% over-abstention is the price of that precision. Reading either cell as an operating-point result would be reading the wrong layer.

**With more time**, in the order the taxonomy justifies: finish the sixteen cells, starting with the contextualisation column, because that is where the largest diagnosed class can move and a null result there is equally informative; run the ten sweep points, since the chunk-size curve is the cleanest answer to the brief's chunking comparison and the hop curve decides whether the loop earns its rewrite calls; add the parent-chunk generation variant, which needs one citation field and no re-index; enable the judge on the headline cells so citation precision stops meaning containment; have a human read the 60 golden items, the one threat no amount of compute removes; and write the per-mode threshold back into each cell, so the abstention columns measure the operating point they claim to. Then the metric table will say more than a direction, and the taxonomy will say which of those five was worth doing.

## 5 References

1. Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., & Liu, Z. (2024). *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation.* arXiv:2402.03216. (The `BAAI/bge-m3` embedder: 1,024 dimensions, 8,192-token window.)
2. Günther, M., Mohr, I., Williams, D. J., & Wang, B. (2024). *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models.* arXiv:2409.04701. (The late-chunking level, §2.2.)
3. Anthropic (2024). *Introducing Contextual Retrieval.* https://www.anthropic.com/research/contextual-retrieval. (The contextual-prefix level, and the −49% top-20 retrieval-failure figure with its −67% reranked variant, as catalogued in `docs/research/rag-systems-survey.md`.)
4. Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. *Proceedings of SIGIR 2009*, 758–759. (The hybrid level's fusion rule.)
5. McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika*, 12(2), 153–157. (The paired test of §2.4.)
6. Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems 33*. (The pattern; Topic 5 reference.)
7. Gao, Y., Xiong, Y., Gao, X., et al. (2023). *Retrieval-Augmented Generation for Large Language Models: A Survey.* arXiv:2312.10997. (Topic 5 reference; the survey frame this project's module table follows.)
8. Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024). *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* arXiv:2309.15217. (Faithfulness and context-relevance definitions, as catalogued in the survey file.)
9. Laurer, M., van Atteveldt, W., Casas, A., & Welbers, K. (2023). Less Annotating, More Classifying: Addressing the Data Scarcity Issue of Supervised Machine Learning with Deep Transfer Learning and BERT-NLI. *Political Analysis.* (The NLI layer's checkpoint `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`.)
10. HashiCorp. Vault documentation, `content/vault/v1.21.x`, commit-pinned snapshot `vault-1.21.x-1817bdfe` of `hashicorp/web-unified-docs`. https://developer.hashicorp.com/vault/docs. (The knowledge base.)
11. Qdrant. *Vector database documentation.* https://qdrant.tech/documentation/. (Dense and sparse collection storage, §2.2.)
12. Chainlit. *Documentation.* https://docs.chainlit.io/. (The demo screen and its custom citation element, §A.5.)
13. Deepset. *Haystack evaluators documentation.* https://docs.haystack.deepset.ai/docs/evaluators. (Recall@k, MRR and nDCG@k as implemented for §3.1.)
14. Thakur, N., Reimers, N., Rücklé, A., Srivastava, A., & Gurevych, I. (2021). *BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models.* arXiv:2104.08663. (nDCG@10 as the retrieval headline metric.)

Metrics are additionally defined in `GLOSSARY.md` (`Retrieval Hit`, `Citation Precision`, `Abstention`, `Faithfulness`), which the experiment code takes its vocabulary from. `docs/research/rag-systems-survey.md` catalogues which of these metrics mature systems actually implement: citation precision and recall are the ones no surveyed open-source harness ships, and contextual retrieval and late chunking are the ones no surveyed open-source harness ships either — the two levels this project tests.

## Appendix A

### A.1 The full matrix row set

Every value below is copied from `reports/matrix.md`, which is generated from the run directories; `missing` is the generator's own marker and means the cell produced no run that could be read. All eighteen declared cells are printed, in design order, whether or not they produced a run.

| # | cell | run id | hit@10 | cit. prec. | cit. rec. | ¥/1k |
|---|---|---|---|---|---|---|
| 1 | `cell-fixed-dense-plain` | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | 0.8500 | 1.0000 | 0.8750 | 9.2745 |
| 2 | `cell-fixed-dense-contextual_prefix` | missing | missing | missing | missing | missing |
| 3 | `cell-fixed-dense-late_chunking` | missing | missing | missing | missing | missing |
| 4 | `cell-fixed-hybrid-plain` | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | 0.9000 | 0.9846 | 0.9500 | 8.4638 |
| 5 | `cell-fixed-hybrid-contextual_prefix` | missing | missing | missing | missing | missing |
| 6 | `cell-fixed-hybrid-late_chunking` | missing | missing | missing | missing | missing |
| 7 | `cell-fixed-rerank-plain` | unfinished, no `metrics.json` (`…125648-57be667d`) | missing | missing | missing | missing |
| 8 | `cell-fixed-rerank-contextual_prefix` | missing | missing | missing | missing | missing |
| 9 | `cell-fixed-rerank-late_chunking` | missing | missing | missing | missing | missing |
| 10 | `cell-recursive_parent_child-dense-plain` | missing | missing | missing | missing | missing |
| 11 | `cell-recursive_parent_child-dense-contextual_prefix` | missing | missing | missing | missing | missing |
| 12 | `cell-recursive_parent_child-dense-late_chunking` | missing | missing | missing | missing | missing |
| 13 | `cell-recursive_parent_child-hybrid-plain` | missing | missing | missing | missing | missing |
| 14 | `cell-recursive_parent_child-hybrid-contextual_prefix` | missing | missing | missing | missing | missing |
| 15 | `cell-recursive_parent_child-hybrid-late_chunking` | missing | missing | missing | missing | missing |
| 16 | `cell-recursive_parent_child-rerank-plain` | missing | missing | missing | missing | missing |
| 17 | `cell-recursive_parent_child-rerank-contextual_prefix` | missing | missing | missing | missing | missing |
| 18 | `cell-recursive_parent_child-rerank-late_chunking` | missing | missing | missing | missing | missing |

The columns this table omits — MRR, nDCG@10, span hit rate, over-abstention rate, abstention recall, p50/p95 latency, the cell's own abstain threshold, item counts — are all in `reports/matrix.md`. The two finished cells in full:

| metric | `cell-fixed-dense-plain` | `cell-fixed-hybrid-plain` |
|---|---|---|
| items evaluated | 60 | 60 |
| `generate.abstain_score_threshold` | 0.2000 | 0.0100 |
| MRR | 0.4817 | 0.6529 |
| nDCG@10 | 0.5697 | 0.7163 |
| span hit rate | 1.0000 | 0.9846 |
| over-abstention on answerable | 0.1000 | 0.0500 |
| abstention recall on near-misses | 1.0000 | 1.0000 |
| p50 / p95 latency (ms) | 17.3 / 21.3 | 39.9 / 7502.5 |

Bootstrap intervals (10,000 resamples, seed `20261030` mixed with the cell name, percentile, 95%) for the same two cells, from `reports/significance.md`:

| Cell | hit@10 [CI] | MRR [CI] | nDCG@10 [CI] | cit. prec. [CI] | cit. rec. [CI] | over-abst. [CI] |
|---|---|---|---|---|---|---|
| dense / plain | 0.8500 [0.7250, 0.9500] | 0.4817 [0.3669, 0.5986] | 0.5697 [0.4626, 0.6740] | 1.0000 [1.0000, 1.0000] | 0.8750 [0.7750, 0.9750] | 0.1000 [0.0250, 0.2000] |
| hybrid / plain | 0.9000 [0.8000, 0.9750] | 0.6529 [0.5458, 0.7562] | 0.7163 [0.6170, 0.8083] | 0.9846 [0.9524, 1.0000] | 0.9500 [0.8750, 1.0000] | 0.0500 [0.0000, 0.1250] |

Citation precision for the dense cell is reported over 35 claims and citation recall over 40 items — the denominators differ because a cell can answer an item with several claims or with none.

### A.2 Artifact index

| Artifact | Answers |
|---|---|
| `runs/<run_id>/` | One configuration: resolved config, git SHA, corpus snapshot, models, prompt hash, `predictions.jsonl`, `citations.jsonl`, `chunks.jsonl`, `metrics.json`, timings, cache stats. |
| `reports/matrix.{md,csv,json}` | The 18-cell table, main effects, interactions, digest drift, orphan and unfinished runs. |
| `reports/significance.{md,csv}` | Bootstrap intervals per cell, McNemar contrasts per factor, per-stratum detail. |
| `reports/judges.{md,csv}` | κ per verification layer and the NLI × judge confusion grid. |
| `reports/cost.{md,csv}` | Tokens by component, CNY per 1,000 questions, index size, latency. |
| `reports/abstention/*` | Per-mode precision-recall CSVs and figures, chosen working points with their transforms, near-miss examples at the chosen point. |
| `reports/sweeps/{k,chunk,hops}.*` | The three sensitivity curves; all points pending at this snapshot. |
| `reports/baselines/*` | The generator probe, the window-cost projection, the model catalogue. |
| `notes/error-taxonomy.md` | The nine classes and every assigned failure. |
| `notes/golden-v1-authoring.md` | How the 60 items were drafted, revised and verified. |
| `notes/prefix-audit.md` | The 20-prefix rubric audit and the prefix cache economics. |
| `notes/judge-calibration.md` | The 30 labelled claims and each layer's verdict. |
| `docs/adr/0001`–`0017` | The seventeen decisions this report cites. |
| `assets/report/*.png` | The four figures, redrawn from the files above by `.scratch/topic5-rag/report_figures.py`. |

### A.3 Reproduction

```bash
python -m ragqa.selftest                                    # offline test suite, no network, no GPU
python scripts/run_matrix.py                                # the 18 cells, resumable
python scripts/run_sweeps.py --emit --check                 # emit + gate the ten sweep cells
python scripts/run_sweeps.py                                # execute pending sweep points
python scripts/run_baselines.py --measure-window runs/<ref>  # window-cost.json, no model calls
python scripts/calibrate_judges.py                          # both judge layers, cached
python -m ragqa aggregate --runs <runs-root> --out reports   # every table and figure under reports/
python -m ragqa serve --config configs/real_llm.yaml         # the demo screen
```

A run is reproducible because responses are cached by `(model, messages, max tokens, temperature)`, not because temperature is 0: two consecutive temperature-0 runs of the same 20 items produced 17 and then 21 claims (ADR-0012). The cache is what makes a `run_id` replayable byte for byte, and `cache_stats.json` records the hits and misses that say whether it did.

### A.4 Golden set authoring and verification

Questions, reference answers and evidence anchors were drafted by `llm:deepseek-v4.1-flash@2026-10-30` and emitted by `scripts/golden_emit.py` from a `(doc_id, keyword)` specification, so no quote was ever typed from memory. Six items changed between first draft and shipping file: one anchor that existed only split across two source lines, a table anchor that resolved to the heading above it, a truncated line fragment re-anchored to a complete sentence, two near-misses that turned out to be answerable and were replaced, and one `near_miss_doc` naming a document absent from the snapshot. The validator checks schema, unique ids, the quota table, `doc_id` existence, quote-verbatim after whitespace normalisation, quote uniqueness across the corpus, and question length; all 49 evidence quotes are distinct, so no two items share an anchor. v0 remains unchanged, including one defect found after the fact (its `U005` asserts the corpus never names Terraform resources, and it does), because a golden version is immutable.

### A.5 The demo

One Chainlit screen, one configuration (`configs/real_llm.yaml`), five questions. The process loads corpus, chunks, `bge-m3`, the Qdrant collection, the BM25 branch, the reranker and the generator once (38.9 s, 2,203 chunks) and serves. Each claim carries a `[n]` marker that is an `Action`, not a link: clicking it sends the citation payload (`marker`, `claim_id`, `chunk_id`, `doc_id`, `span_start`, `span_end`) and the side panel is rebuilt from the chunk as it exists in the running process, so a click cannot show a stale copy; the payload carries no chunk text by design. The five questions exercise five behaviours — a claim per sentence with three separate markers (A001), the shortest possible answer (A004), a claim taken from a table row rather than prose (A007), the pipeline withholding one of its own claims because the quote was not in the cited chunk (A009: `quote_not_in_chunk`, no marker, failure class shown), and a near-miss that abstains although its best chunk scores 0.669, above the threshold (U008). Two offline paths exist for a demo machine without a network: replay from `data/cache/llm.sqlite`, or the fixture configuration (`configs/smoke.yaml`), which shows the same screen, markers and abstention path on eleven fixture chunks.

<!-- pagebreak -->

## 6 Individual Contributions

| # | Member | Contribution | Ratio | Signature |
|---|---|---|---|---|
| 1 | [MEMBER 1] | [CONTRIBUTION] | [ %] | ______________________________ |
| 2 | [MEMBER 2] | [CONTRIBUTION] | [ %] | ______________________________ |
| 3 | [MEMBER 3] | [CONTRIBUTION] | [ %] | ______________________________ |
| 4 | [MEMBER 4] | [CONTRIBUTION] | [ %] | ______________________________ |
| 5 | [MEMBER 5] | [CONTRIBUTION] | [ %] | ______________________________ |
| 6 | [MEMBER 6] | [CONTRIBUTION] | [ %] | ______________________________ |
| 7 | [MEMBER 7] | [CONTRIBUTION] | [ %] | ______________________________ |
| 8 | [MEMBER 8] | [CONTRIBUTION] | [ %] | ______________________________ |
| | **Total** | | **100 %** | |

We confirm that the ratios above state each member's individual contribution to this project, that the sum is 100%, and that every member has read and approved this report.

Group representative: ______________________________  Date: ______________

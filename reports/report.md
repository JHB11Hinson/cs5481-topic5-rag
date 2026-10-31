# A Documentation Knowledge Base That Cites What It Says, and Says Nothing When It Cannot

**CS5481 Data Engineering — Group Project, Topic 5 · 24 November 2026**

Knowledge base: Vault 1.21.x documentation, snapshot `vault-1.21.x-1817bdfe` (1,268 documents, 5.62 M characters, commit-pinned). Code: `ragqa/` (Python); demo: one Chainlit screen. Every number below names a `runs/<run_id>/` directory or a row of the generated `reports/` bundle; §A.2 indexes the artifacts.

## 1 Introduction

The brief asks for question answering over a private document set in which every claim is tied to a retrieved source and a missing answer is stated instead of invented. This report is about the engineering half of that problem: how a chunk is formed, contextualised and narrowed, and how a citation is *checked* rather than believed. Our answer to the last question is a three-layer verifier whose first layer is arithmetic — a claim must quote text that occurs inside the chunk it cites (ADR-0004) — and our answer to the first three is an 18-cell factorial matrix over chunk strategy, retrieval mode and contextualisation, measured against a 60-item Golden QA Set.

All eighteen cells have now finished. Retrieval hit@10 averages **0.8792** for hybrid and **0.8792** for reranked retrieval against **0.6583** for dense; contextualisation separates, with `plain` at 0.8833 and `contextual_prefix` at 0.8750 against **0.6583** for late chunking; chunk strategy does not, averaging 0.7944 for fixed and 0.8167 for recursive parent-child, and none of the nine paired chunk comparisons moves hit@10 by more than **0.0500** (p ≥ 0.5000). Two contrasts clear the paired test: reranked retrieval *loses* to hybrid on grounded citation (**p = 0.035698**) and late chunking loses to plain on citation (**p = 0.000007**) and on the abstention decision (p < 0.000001). Answer correctness against the reference answer runs 0.7500–0.9000 over the forty answerable items in the twelve cells that do not use late chunking (0.4250–0.9000 over all eighteen) and 0.8205–0.9231 over the items those twelve cells chose to answer (0.7083–0.9474 over all eighteen), at **¥8.4638 per 1,000 questions** — run `grid-fixed-hybrid-plain-20261030T125429-6170ae66`.

Contributions, in the order the experiments support them: a **citation contract checked in code before it is judged by a model** (structured claims carrying `doc_id`, `chunk_id` and a span; containment, then NLI, then a judge calibrated on 30 hand labels, §3.4); an **18-cell design with paired tests and intervals fixed before the runs** (ADR-0005), whose generator prints `missing` rather than a guess and which now yields two null results worth as much as its two positive ones; a **calibrated abstention path** — an 18-point precision-recall sweep per retrieval scale with the working-point rule fixed in advance, and the raw threshold written back per scale because three retrieval modes do not share a score scale (§3.2); an **error taxonomy of nine classes** assigned by the earliest layer that lost the answer, which is what §4 argues from rather than from the metric table; and a **cost accounting that refuses the obvious argument**, because long context is *not* the expensive baseline on this corpus (§3.7).

The brief's five requirements map one-to-one: data preparation and the chunking comparison (§2.1, §3.6), storage (§2.2), retrieval (§2.2, §3.1), grounded generation with per-claim citation and explicit abstention (§2.3, §3.2), and evaluation over a test set of at least 20 pairs — ours has 60, reporting **retrieval hit rate** (§3.1) and **answer correctness** (§3.8).

## 2 Methodology

### 2.1 Corpus, parsing and chunking

The knowledge base is the Vault documentation at `content/vault/v1.21.x` in `hashicorp/web-unified-docs`, pinned by commit SHA (ADR-0008) and ingested by blobless sparse checkout. It is parsed twice — structure-aware and stripped plain text (ADR-0007) — leaving 1,268 documents, 5,622,957 characters, median 1,573 and mean 4,434.5 (`reports/baselines/window-cost.json`). Chunking is a two-level factor. **Fixed** cuts character windows with a 64-word overlap. **Recursive parent-child** accumulates units (sentence, table, fenced code block) to a child budget, records the heading path of the unit starting each chunk, and groups consecutive children into a 2× parent, keeping tables and code blocks atomic (ADR-0010). Heading-bounded splitting was rejected on measurement: 9,444 sections across 1,268 documents with a median of 31 words gave children sized by heading density (mean 56–67 words at a 128, 192 or 256-word target) and parents indistinguishable from children. `fixed` yields 2,318 chunks and a 22.9 MiB index; `recursive_parent_child` yields 2,203 chunks, 21.7 MiB and 1,536 parents. Shared include fragments referenced by several pages are indexed once, with the referring page keeping a `[shared partial: …]` marker, so one alert box cannot become hundreds of near-identical chunks (ADR-0009).

### 2.2 Storage, retrieval levels and contextualisation levels

Chunks and embeddings live in Qdrant, dense and sparse, keyed to one corpus snapshot. Embedding and reranking are local (`BAAI/bge-m3`, 1,024 dimensions, 8,192-token window; `bge-reranker-v2-m3`); only generation and judging are hosted (ADR-0001). Retrieval has three levels — **dense**, **hybrid** (dense + BM25 fused by reciprocal rank fusion), and **hybrid + cross-encoder rerank** — at `k=10`, and every level keeps at least `k` candidates after its last stage (`rerank_top = max(k, 12)`), because a stage returning 8 candidates while the metric counts 10 measures truncation, not retrieval (ADR-0011). Contextualisation has three levels: **plain**; a **contextual prefix**, one generated sentence situating the chunk in its document, prepended before embedding and audited against a four-criterion rubric on 20 of the 2,203 cached prefixes; and **late chunking**, which encodes each document in 2,048-token windows with 256 overlap and pools each chunk's vector from the token states covering its span (ADR-0015) — the whole-document variant peaked at 5.56 GB of a 6.00 GB card, which is why the window exists. The prefix is used on the index side only and never shown to the generator (ADR-0013): if the model could quote it, a correct answer would be recorded as a containment failure, since the prefix exists nowhere in the chunk.

### 2.3 Grounded generation and the citation contract

The generator returns JSON: an `answerable` flag and claims carrying `text`, `doc_id`, `chunk_id`, `span_start`, `span_end` and a verbatim `quote`. **Containment** is arithmetic — the quote must occur in the cited chunk and the offsets must delimit it — and only claims that survive reach the **NLI cross-encoder** (`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`) and the **hosted judge** (`deepseek-v4-pro`). Abstention is explicit: a statement that the knowledge base does not answer, with the best-scoring chunk shown beside it, and a written reason in every case we inspected. The generator receives the retrieved child, not its parent (ADR-0017): a 1,024-word parent with a 60-word citation would fail containment on parent-only text, and the failure rate would measure bookkeeping rather than the model. `retrieved[].parent_id` is carried through so the parent can be used later without re-indexing.

### 2.4 The 18-cell design, the golden set and the statistics

The matrix is chunk strategy (2) × retrieval mode (3) × contextualisation (3) = 18 cells, each a configuration file run by one code baseline at one pinned commit and each writing an immutable `runs/<run_id>/` (ADR-0003); cells are joined to runs by a config digest recomputed from the cell's YAML, never by timestamp. **All eighteen cells finished**, with zero digest drift, zero orphan runs and zero unreadable ones (`reports/matrix.md`). The **60-item Golden QA Set** (ADR-0005) is identical for every cell:

| Stratum | Items | Difficulty |
|---|---|---|
| `fact_lookup` (A001–A010) | 10 | easy 4, medium 6 |
| `param_value` (A011–A018) | 8 | easy 2, medium 6 |
| `table_content` (A019–A026) | 8 | medium 5, hard 3 |
| `multi_hop` (A027–A034) | 8 | hard 8 |
| `concept` (A035–A040) | 6 | medium 6 |
| **answerable** | **40** | easy 6, medium 23, hard 11 |
| `near_miss` (U001–U020) | 20 | easy 4, medium 10, hard 6 |
| **total** | **60** | easy 10, medium 33, hard 17 |

Evidence is anchored as `(doc_id, quoted sentence)` rather than a chunk id, so re-chunking cannot break the set. The 20 near-misses come from five generators — a later release than the snapshot, deployment-specific state, a sibling product's documentation, an undocumented combination of two documented features, and commercial-only facts — each verified to occur zero times in the corpus, and each naming a `near_miss_doc` that does exist so the metadata does not leak the answer. Comparisons are paired by item: McNemar's exact test (two-sided) on discordant pairs, and 10,000-resample percentile bootstrap intervals whose resample unit is the *item*, not the claim (seed `20261030`). Twenty items was the original plan and was too small on both counts: 20 negatives give a 21-point abstention curve rather than a staircase, and at a 0.75-versus-0.90 difference 60 answerable items yield about 12 discordant pairs (10:2, p≈0.04) where 24 yield about 5 (p≈0.38). Set size, not cell count, decides whether any claim here can carry a significance marker.

### 2.5 What we deliberately did not build

| Omitted | Why |
|---|---|
| Graph index (GraphRAG / LightRAG style), ColBERT late interaction, embedding fine-tuning | Each multiplies index cost or needs labelled pairs we do not have, for gains the two stage-2 rankers already chase on a single product's manual (ADR-0002). |
| OCR / table-structure recognition | The source is markdown and MDX: tables arrive as pipe tables, code as fenced text. Layout analysis recovers structure this corpus never lost; what structure is worth is measured instead, by parsing twice (ADR-0007). |
| Prefix inside the generation prompt | Would break containment and confound the contextualisation factor with a prompt change (ADR-0013). |
| Whole-document late-chunking windows; multi-tenant auth; a UI beyond one screen | 5.56 GB of a 6.00 GB card and a 53 k-character document truncated at the window; the brief's challenge is the backend pipeline, and one screen showing citations and abstention is what a demo has to show (ADR-0015). |

## 3 Experiments

### 3.1 The eighteen-cell matrix

Every row is a finished run joined by recomputed config digest. `hit@10` is over the 40 answerable items, `cit. rec.` and `over-abst.` over items, money per 1,000 questions.

| # | chunk | retrieval | context | hit@10 | MRR | cit. rec. | over-abst. | ¥/1k | run id |
|---|---|---|---|---|---|---|---|---|---|
| 1 | fixed | dense | plain | 0.8500 | 0.4817 | 0.8750 | 0.1000 | 9.2745 | `…8ae4eb06` |
| 2 | fixed | dense | prefix | 0.8250 | 0.4180 | 0.8000 | 0.1500 | 9.3053 | `…d947855e` |
| 3 | fixed | dense | late | 0.2750 | 0.1468 | 0.6000 | 0.4000 | 4.7134 | `…76813f02` |
| 4 | fixed | hybrid | plain | 0.9000 | 0.6529 | 0.9500 | 0.0500 | 8.4638 | `…6170ae66` |
| 5 | fixed | hybrid | prefix | 0.8750 | 0.5737 | 0.9000 | 0.0500 | 8.9954 | `…0d58c950` |
| 6 | fixed | hybrid | late | 0.8250 | 0.3909 | 0.8750 | 0.1000 | 6.7740 | `…66c05c39` |
| 7 | fixed | rerank | plain | 0.9000 | 0.6044 | 0.8750 | 0.0250 | 8.7896 | `…57be667d` |
| 8 | fixed | rerank | prefix | 0.8750 | 0.6184 | 0.9500 | 0.0250 | 8.4302 | `…14c0b222` |
| 9 | fixed | rerank | late | 0.8250 | 0.6204 | 0.9250 | 0.0500 | 7.7369 | `…8f5d6ac0` |
| 10 | recursive | dense | plain | 0.8500 | 0.4792 | 0.9000 | 0.0500 | 9.3342 | `…5b0e5d3e` |
| 11 | recursive | dense | prefix | 0.8750 | 0.5045 | 0.9750 | 0.0250 | 9.1211 | `…7ace3fb3` |
| 12 | recursive | dense | late | 0.2750 | 0.1514 | 0.6250 | 0.3500 | 5.0055 | `…9b6dc31d` |
| 13 | recursive | hybrid | plain | 0.9000 | 0.6521 | 1.0000 | 0.0000 | 8.5350 | `…e4e09d4e` |
| 14 | recursive | hybrid | prefix | 0.9000 | 0.6432 | 0.9750 | 0.0250 | 8.4614 | `…effcbe64` |
| 15 | recursive | hybrid | late | 0.8750 | 0.3982 | 0.9500 | 0.0500 | 6.7107 | `…0cecad68` |
| 16 | recursive | rerank | plain | 0.9000 | 0.5985 | 0.9000 | 0.0250 | 9.5427 | `…dc28d910` |
| 17 | recursive | rerank | prefix | 0.9000 | 0.5880 | 0.8500 | 0.0500 | 8.9514 | `…d112558a` |
| 18 | recursive | rerank | late | 0.8750 | 0.6180 | 0.8500 | 0.0750 | 7.2902 | `…ddf8886b` |

Source: `reports/matrix.md`; the full run ids, plus nDCG@10, span hit rate, abstention recall and latency, are in §A.1 and the CSV.

**Main effects on hit@10**, each mean carrying its cell count: chunk `fixed` 0.7944 over 9 cells and `recursive_parent_child` 0.8167 over 9; retrieval `dense` 0.6583 over 6, `hybrid` 0.8792 over 6, `rerank` 0.8792 over 6; contextualisation `plain` 0.8833 over 6, `contextual_prefix` 0.8750 over 6, `late_chunking` 0.6583 over 6 (`reports/matrix.md`). Citation precision moves the other way on the same rows — dense 0.9863, hybrid 0.9701, rerank 0.9593 — so the retrieval level that finds less, cites more narrowly.

**Interactions.** Two of the three two-way terms are near zero (chunk × retrieval within ±0.0028, chunk × contextualisation within ±0.0111), which is what additivity on this metric looks like. The one that is not is retrieval × contextualisation at the dense/late-chunking corner: 0.2750 observed against 0.5110 predicted additively, **i = −0.2361**, while the same corner at `plain` beats prediction by +0.1139. Late chunking does not damage retrieval everywhere; it destroys the dense branch specifically, and §3.6 shows the cause is pooling geometry rather than chunking.

**Contrasts.** Nine paired contrasts are computed over pooled discordant items (`reports/significance.md`). Reranked retrieval ties hybrid on hit@10 but loses on grounded citation, 8 items to 20, **p = 0.035698**. `contextual_prefix` is null against `plain` on every outcome (citation p = 0.823803, abstention p = 0.581055) — the prefix experiment did not pay. `late_chunking` loses to `plain` decisively on grounded citation (5 to 32, **p = 0.000007**) and on the abstention decision (1 to 32, p < 0.000001), while its retrieval contrast ties, which is the same corner effect seen from the other side. Interval rows for `hit@10`, MRR and nDCG@10 in this bundle print a degenerate [0, 0] for all 18 cells — an aggregate defect we report rather than paper over (§3.9) — so retrieval intervals are not quoted here; the citation and abstention intervals are sound and are in §A.1.

### 3.2 Abstention as a calibrated decision

Each item's top retrieval score is swept over an 18-point grid on [0.2, 0.9]; a positive is an answerable item that should be answered, a negative a near-miss that should be refused. The modes do not share a scale — cosine, an RRF fused sum around 1/(60+rank), a cross-encoder score in [0, 1] — and one number across them is visibly destructive: a hybrid run shipped with 0.20 abstained on all 20 items of its run because the RRF scale never reaches 0.20, while the same config key at 0.01 answered all 20. So the sweep runs in a normalised space (z-score then standard-normal CDF for hybrid and rerank; identity for cosine) and reports each point's raw equivalent, the only value that can be written back into a configuration. The working-point rule was fixed first: maximise F1 of the answer class subject to over-abstention on answerable items ≤ 0.05, ties to the larger threshold.

| scale | t (normalised) | raw threshold | precision | recall | over-abstain | under-abstain | answered | near-misses answered |
|---|---|---|---|---|---|---|---|---|
| dense | 0.5706 | 0.570600 | 0.691 | 0.950 | **0.050** | 0.850 | 38 of 40 | 17 of 20 |
| hybrid | 0.2824 | 0.028606 | 0.661 | 0.925 | 0.075 | 0.950 | 37 of 40 | 19 of 20 |
| rerank | 0.2000 | 0.426134 | 0.739 | 0.850 | 0.150 | 0.600 | 34 of 40 | 12 of 20 |

Source: `reports/abstention/working-points.json`, fitted on the v1 sweep (60 items, 40 answerable, 20 near-misses). **Only the dense scale can satisfy the 0.05 over-abstention budget**, and only just: at t = 0.5706 it refuses 2 of 40 answerable items and still answers 17 of 20 near-misses. Hybrid and rerank are **budget-infeasible at all 18 points**, so the rule's pre-registered fallback fired and the table reports the smallest achievable over-abstention it could reach, 0.075 and 0.150. Hybrid cannot separate for a structural reason: its score is a reciprocal-rank sum, so the curve is a plateau before it is a curve — three consecutive grid points (t = 0.2, 0.2412, 0.2824) return the identical operating point (precision 0.6607, recall 0.9250) because no item's top score falls between their raw equivalents, and an unanswerable question that both branches rank first is indistinguishable from a real one by this number. Rerank answers 12 of 20 near-misses at its floor: a cross-encoder scores relevance, and a near-miss is by construction relevant.

![](assets/report/fig1-abstention.png)

*Figure 1 — precision-recall per score scale with the chosen working point. Source: `reports/abstention/{dense,hybrid,rerank}-pr.csv`.*

**What the matrix's abstention columns actually measure.** The shipped cells ran with `generate.abstain_score_threshold` at 0.2 (dense), 0.01 (hybrid) and 0.0 (rerank) — three levels, three scales — and they compute that comparison, but the generator's refusals do not come from it: the abstentions in the matrix are decisions the language model wrote, each with a reason, while the calibrated thresholds are an alternative policy the shipped cells never apply. Both statements are true at once and neither is a defect: all twenty near-misses were refused in **every one of the eighteen cells** (abstention recall 1.0000 throughout), and over-abstention on answerable items ranges from 0.0000 (`recursive/hybrid/plain`) to 0.4000 (`fixed/dense/late_chunking`) — a spread that tracks retrieval quality, not a threshold. Reading either column as an operating-point result would be reading the wrong layer.

### 3.3 The three sensitivity curves

Three one-parameter families are declared around one reference cell (`configs/grid/cell-recursive_parent_child-rerank-plain.yaml`), so a difference between two points is attributable to the swept key alone; every point holds the same 40 answerable items, corpus, embedder, truncation and prices.

| Curve | Swept key | Points | Generation calls | Status |
|---|---|---|---|---|
| depth | `retrieval.k` | 5, 10, 20, 40 | 160 | 0 of 4 finished |
| chunk size | `chunk.size` | 256, 512, 1024 | 120 | 0 of 3 finished |
| hops | `retrieval.hops` | 1, 2, 3 | 120 | 0 of 3 finished |

**All ten points are pending at this snapshot: no curve is reported as a curve** (`reports/sweeps/{k,chunk,hops}.{md,csv}`). What is fixed in advance is the expected shape and the rule that will read it. Depth should rise while a wider net can still reach the evidence and flatten after that. Chunk size should show citation precision peaking before citation recall, with the 1,024-word point a lower bound because `embed.max_seq_length` is 1,024 tokens. Hops should show the second round recovering what the first put below the trigger (`retrieval.trigger_threshold = 0.426134`, the published rerank working point, so a rewrite fires exactly on rounds the calibration would refuse); the loop stops paying at the first hop whose marginal ¥ per recall point is at least the previous hop's, and "the loop never fires" is itself a result returning hop 1 at about ¥1.00 per 1,000 questions.

### 3.4 Judge agreement

Thirty claims — twenty verbatim from real generation runs, ten controlled negatives built by one documented edit to a verbatim claim — were labelled by hand against the full cited chunk. The bar, κ ≥ 0.60, was fixed before any judge ran.

| Layer | n | agreement | precision | recall | κ | role |
|---|---|---|---|---|---|---|
| containment (string) | 30 | 0.667 | 0.667 | 1.000 | 0.000 | advisory |
| NLI cross-encoder | 30 | 0.833 | 0.826 | 0.950 | 0.595 | advisory |
| hosted judge (`deepseek-v4-pro`) | 30 | 0.933 | 1.000 | 0.900 | 0.857 | **gates reporting** |

Source: `reports/judges.md`, recomputed from stored verdicts. The judge clears the bar with no false-positive call in 30 rows; its two misses are false negatives on true claims (a chain compression, and a sentence at the very end of a long chunk), the honest description of a conservative layer. The NLI layer misses at 0.595, and the decision does not rest on that 0.005 — with 30 rows the standard error of κ is about ±0.18, so 0.595 and 0.60 are one number measured once. It rests on direction: five claims are `nli_only` and none is `judge_only`, so every disagreement inflates support, and a layer whose only errors push the headline number up cannot gate it. **No matrix cell ran with the judge enabled**, so §3.1's citation columns are containment numbers — "the quoted span occurs in the cited chunk", not "the citation supports the claim". The judge costs **¥1.45 per 1,000 claims** (§3.7).

### 3.5 The error distribution

Fourteen failures were hand-assigned across the two `plain` cells — one dense, one hybrid — from 18 candidates, after an abstention caused by a retrieval miss was counted as that miss's symptom rather than as a second failure. The nine classes were fixed before the runs were inspected, and each failure is assigned to the earliest layer that lost the answer.

| Class | dense / plain | hybrid / plain | Total |
|---|---|---|---|
| `retrieval-document-miss` | 4 | 2 | 6 |
| `retrieval-chunk-miss` | 2 | 2 | 4 |
| `generator-over-abstention` | 1 | 1 | 2 |
| `citation-quote-not-in-chunk` | 0 | 1 | 1 |
| `generation-parse-failure` | 1 | 0 | 1 |
| four classes with no instance (`context-budget-drop`, `generator-under-abstention`, `citation-span-out-of-bounds`, `citation-chunk-not-retrieved`) | 0 | 0 | 0 |
| **total** | **8** | **6** | **14** |

Source: `notes/error-taxonomy.md`, drawn in Figure 2. **Ten of the fourteen are retrieval failures and they are two different failures**: six document misses, where no chunk of the evidence document reached the returned depth, and four chunk misses, where the right document arrived and the passage did not. The four remaining are one fabricated span, one parse failure and two over-abstentions. This classification is a hand audit of two cells, not of eighteen; the 26 remaining rows of the ticket's 40 are reported as a shortfall rather than padded, and the class that must stay empty is `context-budget-drop`, which needs a hit at rank 9 or 10 when `retrieval.k` is 10 and `llm.context_chunks` is 8.

![](assets/report/fig2-error-classes.png)

*Figure 2 — hand-assigned failures per class, per cell. Source: `notes/error-taxonomy.md`; runs `…8ae4eb06`, `…6170ae66`.*

### 3.6 Chunking strategy, measured nine times

The brief asks for at least two chunking strategies compared on retrieval quality. Each of the nine pairs below is one retrieval mode and one contextualisation level with **only `chunk.strategy` differing**, on the same 60 items, so a difference is attributable to chunking; the deltas are `recursive_parent_child` minus `fixed` (`reports/chunking.json`, drawn in `notes/chunking-comparison.md`).

| pair (retrieval / context) | Δhit@10 | ΔMRR | Δcit. rec. | p (hit) | p (supported citation) |
|---|---|---|---|---|---|
| dense / plain | 0.0000 | −0.0025 | +0.0250 | 1.0000 | 1.0000 |
| dense / contextual_prefix | +0.0500 | +0.0865 | +0.1750 | 0.5000 | **0.0156** |
| dense / late_chunking | 0.0000 | +0.0046 | +0.0250 | 1.0000 | 1.0000 |
| hybrid / plain | 0.0000 | −0.0008 | +0.0500 | 1.0000 | 0.5000 |
| hybrid / contextual_prefix | +0.0250 | +0.0695 | +0.0750 | 1.0000 | 0.2500 |
| hybrid / late_chunking | +0.0500 | +0.0073 | +0.0750 | 0.5000 | 0.2500 |
| rerank / plain | 0.0000 | −0.0059 | +0.0250 | 1.0000 | 1.0000 |
| rerank / contextual_prefix | +0.0250 | −0.0304 | −0.1000 | 1.0000 | 0.2188 |
| rerank / late_chunking | +0.0500 | −0.0024 | −0.0750 | pending | pending |

Source: `reports/chunking.json` for eight pairs, `notes/chunking-comparison.md` for the significance rows; the ninth pair's deltas are the difference between `reports/matrix.md` rows 9 and 18, and its per-item discordance had not entered the bundle when it was generated.

**Retrieval quality does not move.** The largest movement in hit@10 anywhere is +0.0500 — two items of forty — and no paired test on retrieval comes near significance (p ≥ 0.5000). **Citations move, but not consistently**: `recursive_parent_child` gains citation coverage in six of nine pairs and loses it in two, and only one pair separates (dense/contextual_prefix, +7 items, p = 0.0156), so the sign of the effect depends on the interaction of chunking with contextualisation rather than on chunking itself.

**What chunking did do, in mechanism numbers** (`reports/chunking.json`, recomputed from each chunk set at the pair's 512-token budget): 2,203 recursive children against 2,318 fixed; mean 312 tokens against 328, p95 543 against 512; **477 recursive children over budget, of which 86.8% carry a table row or a code fence** — the splitter refused to break them and paid the budget instead; and the share of chunks ending mid-sentence falls from **0.5745 to 0.1865**. So atomicity happened. **The atomic-table hypothesis is not testable on this set**: all eight `table_content` items are hit by both strategies in every pair, so there is no item that keeping a table whole could have rescued, and the eight McNemar tests over those items return p = 1.0000 throughout. What we can say is the weaker, honest thing — on this corpus, chunk boundary criteria change how chunks are built and how often an answer carries a citable span, and do not change what retrieval finds.

### 3.7 Cost, and what the baselines cost

Five configurations ran against the same 60 items: the reference cell and four ablations, each differing from it in exactly one declared factor (the smaller embedder also changes retrieval mode, and is marked as two). Paired McNemar on per-item outcomes.

| run | hit@k | cit. P | cit. R | over-abst. | ¥/1k | factor vs reference |
|---|---|---|---|---|---|---|
| reference `…22270968` | 0.90 | 1.0000 | 0.90 | 0.025 | 9.0993 | — |
| closed book `…bc6b3c50` | 0.90 | 0.0000 | 0.00 | 1.000 | 0.4746 | `baseline.closed_book` |
| long context `…2b10efa0` | 0.90 | 0.0000 | 0.00 | 0.300 | 4.2440 | `baseline.long_context` (+ cap) |
| all-MiniLM-L6-v2 `…e88cf6b4` | **0.65** | 0.9592 | 0.75 | 0.175 | 7.7827 | `embed.model_id`, `retrieval.mode` |
| cheap generator `…bb87b44b` | 0.90 | 0.8704 | 0.875 | 0.025 | 4.7002 | `llm.model_generate` |

Source: `reports/baselines/table.{md,json}`. Four readings. **Retrieval is what the embedder buys**: swapping to `all-MiniLM-L6-v2` (384 dimensions, 256 positions) drops hit@k from 0.90 to **0.65**, 13 items lost against 3 gained, p = 0.02127, with citation support falling 6-to-0 at p = 0.03125 — the same collapse that dominates §4. **Long context is cheaper than the reference cell**, ¥4.2440 against ¥9.0993 per 1,000 questions, not three times more expensive: the gap is **2.0×**, and the projection in Figure 3 reproduces it (¥4.77 for a 20,000-character cap against ¥9.54 for eight pasted chunks, ratio 2.00). Its 36-to-0 citation-containment loss (p = 3e-11) is the real price, and it is structural: the prompt contains no chunk ids, so a claim cites a document and `verify.check_claims` files it as `chunk_not_retrieved`. **Closed book is uninformative by construction** — the system prompt orders the model to answer only from the provided chunks, so with the block emptied a compliant model declines (36-to-0, p = 3e-11) — and bounds the value of the context block under this prompt, not the model's knowledge. The cheap generator (`gpt-6-luna`) keeps retrieval and loses 4 items of citation support against 3 (p = 1.0) at half the money, which is a business claim and not a headline.

![](assets/report/fig3-prompt-shape-cost.png)

*Figure 3 — projected CNY per 1,000 questions by prompt shape, with mean prompt tokens. Source: `reports/baselines/window-cost.json`.*

On the matrix cells themselves, money per 1,000 questions runs ¥4.7134–¥9.5427, with tokens as the only line item: the dense cell spent 415,147 prompt and 35,261 completion tokens for ¥0.5565 and the hybrid cell 387,766 and 29,952 for ¥0.5078 (`reports/cost.md`). Embedding and reranking are local, so their cost is electricity. Beside it: the prefix warm-up over 2,203 chunks cost ¥0.373 and the rerun with the cache warm ¥0.000 with 2,203 hits, which is what makes that A/B a comparison rather than two samples; judge calibration cost ¥0.0436 for 30 calls, **¥1.4519 per 1,000 claims** (`notes/judge-calibration.metrics.json`); and grading answer correctness for the whole matrix cost ¥0.3104 for 656 judge calls (§3.8). **The latency columns do not measure serving latency** — the dense cell served 61 of 64 LLM calls from the response cache and the hybrid cell 36 of 60, so a 17.3 ms p50 is a SQLite read rather than a network round trip. Read down the column and it ranks cells by cache luck; a cold-latency table needs cacheless runs.

### 3.8 Answer correctness against the reference answer

Hit rate says whether the evidence arrived; it does not say whether the answer was right. For every answerable item of the set, one hosted judge call (`deepseek-v4-pro`) was asked whether the generated answer agrees with the item's `reference_answer` — answer correctness against a reference, not faithfulness, which is whether the cited chunks support the claims and can be high while the answer is wrong. An abstention counts as incorrect in the all-items figure and leaves the denominator in the answered-only figure, so the two are never folded into one number.

Across the eighteen cells, correctness is **0.4250–0.9000 over all 40 answerable items** and **0.7083–0.9474 over the items each cell answered** (mean 0.8139 over all 40); restricting to the twelve cells without late chunking narrows that to **0.7500–0.9000** and **0.8205–0.9231**. Five cells reach 0.9000 (`fixed/rerank/plain`, `fixed/rerank/late`, `recursive/hybrid/plain`, `recursive/hybrid/late`, `recursive/rerank/plain`), and the floor is the two dense late-chunking cells at 0.4250 and 0.4750, where 16 and 14 of 40 answerable items were refused after late chunking failed to surface evidence — correctness and hit@10 fall together, which is the reassuring direction. Grading every answered item exactly once cost **¥0.3104** (656 calls, 227,829 prompt and 20,608 completion tokens, 243 cache hits); no reply failed to parse, so every answerable item carries a verdict (`reports/correctness.json`, `notes/correctness.md`).

### 3.9 Threats to validity

- **Citation numbers are containment, not support** (§3.4); **abstention in the matrix is the generator's, not the threshold's** (§3.2).
- **The error taxonomy covers two cells, not eighteen** (§3.5): 14 hand-assigned failures against the ticket's 40.
- **Latency is cache-dominated and cost is one run's recorded USD scaled up** (§3.7), not a billing statement.
- **The retrieval interval rows in `reports/significance.csv` are degenerate** — `hit_at_10`, `mrr` and `ndcg_at_10` print 0.0000 [0.0000, 0.0000] for all 18 cells against point estimates of 0.2750–0.9000. We quote the point estimates and withhold those intervals rather than reprint a broken one; the citation, span and abstention intervals are unaffected.
- **Golden v1 was not read by a human.** `verified_by` is `automated:corpus-anchored` on all 60 items: every quote was proven to appear verbatim and exactly once, and every question was written from a sentence read in its document context. Nobody opened the items against the documents, so the set is verified as *text*, not as grading behaviour.
- **The ten sweep points are declared and unrun** (§3.3), and `context-budget-drop` can only appear at rank 9 or 10; if it stays empty across all eighteen cells, the honest conclusion is that the narrowing never bites.

## 4 Discussion

The metric table says hybrid and reranked retrieval tie at 0.8792 hit@10 and beat dense by 22 points; the taxonomy says something more useful. **Ten of the fourteen failures are retrieval failures, and they are two different failures.** Six are document misses, where no chunk of the evidence document reached the returned depth: `docs/concepts/seal` is never retrieved in either cell, and three of the returned documents are overview pages whose prose restates the question without the mechanism. Four are chunk misses, where the right document arrived and the passage did not: `docs/enterprise/replication` reaches ranks 1 and 6 while neither returned chunk contains the failover sentence. Everything else — two over-abstentions, one fabricated span, one parse failure — is four failures in total, and no retrieval tuning touches them.

The distinction makes the next experiment decidable, and the matrix now answers part of it. **Chunk misses are the class chunking is designed to move**, and §3.6 says it does not: boundary criteria change mid-sentence share from 0.5745 to 0.1865 and put 477 over-budget children on the index, and hit@10 does not move. That is a null result with a mechanism behind it rather than an absent one — the passages these items lose are not lost at a sentence boundary, they are lost because the page that holds them never ranks. **Document misses are the class a wider net, a second hop or a graph edge would move**, and they are also the class the smaller embedder destroys: 13 items lost against 3 gained, p = 0.02127. So the ordering of future work is not "more contextualisation" — the prefix A/B is null too, four usable pairs all at p = 1.0000 with deltas inside ±0.0250, one item of forty — but "retrieval, at the document level, with a better representation".

The null results are worth stating as findings rather than apologies, because together they eliminate the two cheapest explanations of the dense–hybrid gap. If chunk boundaries were what mattered, the recursive strategy would have separated somewhere in nine pairs and did not. If index-side context were what mattered, the prefix would have separated in six strata and did not (citation p = 0.823803, abstention p = 0.581055). What did separate is the score scale: reranked retrieval loses 20 items to 8 on grounded citation (p = 0.035698) even though its hit@10 is identical to hybrid's, and late chunking loses 32 to 5 (p = 0.000007). Both are statements about *which* evidence a ranker surfaces, not about how chunks are cut — and they say the cross-encoder, applied on top of an RRF ordering, is throwing away citations that the fused ranking already had.

Two observations cut against our own headline numbers. The matrix's abstention columns look excellent — twenty near-misses refused in all eighteen cells — but that is the generator's judgement, not the calibrated threshold's work (§3.2), and the calibrated point that would refuse 17 of 20 near-misses on the dense scale was never in force. And the best correctness cells sit at 0.9000, which is 36 of 40: the residual four are the taxonomy's over-abstentions and one fabricated span, i.e. the same failures seen from a different instrument. Reading either column as an operating-point result would be reading the wrong layer.

**With more time**, in the order this argument justifies: run the ten sweep points, because the chunk-size curve is the direct test of the one mechanism §3.6 could not test — chunk resolution rather than boundary criteria — and the hop curve is the document-miss remedy the taxonomy nominates; enable the judge on headline cells so citation precision stops meaning containment; add the parent-chunk generation variant, which needs one citation field and no re-index, targeting the two over-abstentions that are joins between two retrieved passages; fix the aggregate's retrieval-interval path; scale the hand taxonomy from two cells to eighteen; and have a human read the 60 golden items, the one threat no amount of compute removes.

## 5 References

1. Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., & Liu, Z. (2024). *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation.* arXiv:2402.03216. (The `BAAI/bge-m3` embedder: 1,024 dimensions, 8,192-token window.)
2. Günther, M., Mohr, I., Williams, D. J., & Wang, B. (2024). *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models.* arXiv:2409.04701. (The late-chunking level, §2.2.)
3. Anthropic (2024). *Introducing Contextual Retrieval.* https://www.anthropic.com/research/contextual-retrieval. (The contextual-prefix level, and the −49% top-20 retrieval-failure figure with its −67% reranked variant, as catalogued in `docs/research/rag-systems-survey.md`.)
4. Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. *Proceedings of SIGIR 2009*, 758–759. (The hybrid level's fusion rule, and the lattice that makes its score a poor confidence, §3.2.)
5. McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika*, 12(2), 153–157. (The paired test of §2.4, §3.6, §3.7.)
6. Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems 33*. (The pattern; Topic 5 reference.)
7. Gao, Y., Xiong, Y., Gao, X., et al. (2023). *Retrieval-Augmented Generation for Large Language Models: A Survey.* arXiv:2312.10997. (Topic 5 reference; the survey frame this project's module table follows.)
8. Es, S., James, J., Espinosa-Anke, L., & Schockaert, S. (2024). *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* arXiv:2309.15217. (Faithfulness and context-relevance definitions, and the separation of correctness from faithfulness, §3.8.)
9. Laurer, M., van Atteveldt, W., Casas, A., & Welbers, K. (2023). Less Annotating, More Classifying: Addressing the Data Scarcity Issue of Supervised Machine Learning with Deep Transfer Learning and BERT-NLI. *Political Analysis.* (The NLI layer's checkpoint `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`.)
10. HashiCorp. Vault documentation, `content/vault/v1.21.x`, commit-pinned snapshot `vault-1.21.x-1817bdfe` of `hashicorp/web-unified-docs`. https://developer.hashicorp.com/vault/docs. (The knowledge base.)
11. Qdrant. *Vector database documentation.* https://qdrant.tech/documentation/. (Dense and sparse collection storage, §2.2.)
12. Chainlit. *Documentation.* https://docs.chainlit.io/. (The demo screen and its custom citation element, §A.5.)
13. Deepset. *Haystack evaluators documentation.* https://docs.haystack.deepset.ai/docs/evaluators. (Recall@k, MRR and nDCG@k as implemented for §3.1.)
14. Thakur, N., Reimers, N., Rücklé, A., Srivastava, A., & Gurevych, I. (2021). *BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models.* arXiv:2104.08663. (nDCG@10 as the retrieval headline metric.)

Metrics are additionally defined in `GLOSSARY.md` (`Retrieval Hit`, `Citation Precision`, `Abstention`, `Faithfulness`), which the experiment code takes its vocabulary from; §3.8 uses the brief's own word for answer correctness and says once what it is measured against. `docs/research/rag-systems-survey.md` catalogues which of these metrics mature systems actually implement: citation precision and recall are the ones no surveyed open-source harness ships, and contextual retrieval and late chunking are the ones no surveyed open-source harness ships either — the two levels this project tests.

## Appendix A

### A.1 The full matrix row set

Every value below is copied from `reports/matrix.md` and `reports/correctness.csv`, which are generated from the run directories. All eighteen declared cells are printed, in design order.

| # | cell | run id | hit@10 | MRR | cit. prec. | cit. rec. | over-abst. | ¥/1k |
|---|---|---|---|---|---|---|---|---|
| 1 | `cell-fixed-dense-plain` | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | 0.8500 | 0.4817 | 1.0000 | 0.8750 | 0.1000 | 9.2745 |
| 2 | `cell-fixed-dense-contextual_prefix` | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | 0.8250 | 0.4180 | 0.9818 | 0.8000 | 0.1500 | 9.3053 |
| 3 | `cell-fixed-dense-late_chunking` | `grid-fixed-dense-late_chunking-20261030T161040-76813f02` | 0.2750 | 0.1468 | 1.0000 | 0.6000 | 0.4000 | 4.7134 |
| 4 | `cell-fixed-hybrid-plain` | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | 0.9000 | 0.6529 | 0.9846 | 0.9500 | 0.0500 | 8.4638 |
| 5 | `cell-fixed-hybrid-contextual_prefix` | `grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950` | 0.8750 | 0.5737 | 0.9844 | 0.9000 | 0.0500 | 8.9954 |
| 6 | `cell-fixed-hybrid-late_chunking` | `grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39` | 0.8250 | 0.3909 | 0.9828 | 0.8750 | 0.1000 | 6.7740 |
| 7 | `cell-fixed-rerank-plain` | `grid-fixed-rerank-plain-20261030T125648-57be667d` | 0.9000 | 0.6044 | 0.9206 | 0.8750 | 0.0250 | 8.7896 |
| 8 | `cell-fixed-rerank-contextual_prefix` | `grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222` | 0.8750 | 0.6184 | 0.9500 | 0.9500 | 0.0250 | 8.4302 |
| 9 | `cell-fixed-rerank-late_chunking` | `grid-fixed-rerank-late_chunking-20261030T163138-8f5d6ac0` | 0.8250 | 0.6204 | 0.9844 | 0.9250 | 0.0500 | 7.7369 |
| 10 | `cell-recursive_parent_child-dense-plain` | `grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e` | 0.8500 | 0.4792 | 0.9577 | 0.9000 | 0.0500 | 9.3342 |
| 11 | `cell-recursive_parent_child-dense-contextual_prefix` | `grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3` | 0.8750 | 0.5045 | 1.0000 | 0.9750 | 0.0250 | 9.1211 |
| 12 | `cell-recursive_parent_child-dense-late_chunking` | `grid-recursive_parent_child-dense-late_chunking-20261030T164237-9b6dc31d` | 0.2750 | 0.1514 | 0.9783 | 0.6250 | 0.3500 | 5.0055 |
| 13 | `cell-recursive_parent_child-hybrid-plain` | `grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e` | 0.9000 | 0.6521 | 0.9571 | 1.0000 | 0.0000 | 8.5350 |
| 14 | `cell-recursive_parent_child-hybrid-contextual_prefix` | `grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64` | 0.9000 | 0.6432 | 0.9753 | 0.9750 | 0.0250 | 8.4614 |
| 15 | `cell-recursive_parent_child-hybrid-late_chunking` | `grid-recursive_parent_child-hybrid-late_chunking-20261030T165835-0cecad68` | 0.8750 | 0.3982 | 0.9365 | 0.9500 | 0.0500 | 6.7107 |
| 16 | `cell-recursive_parent_child-rerank-plain` | `grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910` | 0.9000 | 0.5985 | 1.0000 | 0.9000 | 0.0250 | 9.5427 |
| 17 | `cell-recursive_parent_child-rerank-contextual_prefix` | `grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a` | 0.9000 | 0.5880 | 0.9516 | 0.8500 | 0.0500 | 8.9514 |
| 18 | `cell-recursive_parent_child-rerank-late_chunking` | `grid-recursive_parent_child-rerank-late_chunking-20261030T170813-ddf8886b` | 0.8750 | 0.6180 | 0.9492 | 0.8500 | 0.0750 | 7.2902 |

Answer correctness per cell, same eighteen runs (`reports/correctness.csv`):

| # | cell | accuracy (all 40) [95% CI] | accuracy (answered) | abstentions | correct / answered | ¥ |
|---|---|---|---|---|---|---|
| 1 | fixed/dense/plain | 0.8250 [0.7000, 0.9250] | 0.9167 | 4 | 33/36 | 0.0173 |
| 2 | fixed/dense/prefix | 0.7500 [0.6000, 0.8750] | 0.8824 | 6 | 30/34 | 0.0161 |
| 3 | fixed/dense/late | 0.4250 [0.2750, 0.5750] | 0.7083 | 16 | 17/24 | 0.0117 |
| 4 | fixed/hybrid/plain | 0.8750 [0.7750, 0.9750] | 0.9211 | 2 | 35/38 | 0.0178 |
| 5 | fixed/hybrid/prefix | 0.8750 [0.7750, 0.9750] | 0.9211 | 2 | 35/38 | 0.0175 |
| 6 | fixed/hybrid/late | 0.8500 [0.7250, 0.9500] | 0.9444 | 4 | 34/36 | 0.0166 |
| 7 | fixed/rerank/plain | 0.9000 [0.8000, 0.9750] | 0.9231 | 1 | 36/39 | 0.0181 |
| 8 | fixed/rerank/prefix | 0.8750 [0.7750, 0.9750] | 0.8974 | 1 | 35/39 | 0.0189 |
| 9 | fixed/rerank/late | 0.9000 [0.8000, 0.9750] | 0.9474 | 2 | 36/38 | 0.0179 |
| 10 | recursive/dense/plain | 0.8250 [0.7000, 0.9250] | 0.8684 | 2 | 33/38 | 0.0181 |
| 11 | recursive/dense/prefix | 0.8000 [0.6750, 0.9250] | 0.8205 | 1 | 32/39 | 0.0188 |
| 12 | recursive/dense/late | 0.4750 [0.3250, 0.6250] | 0.7308 | 14 | 19/26 | 0.0127 |
| 13 | recursive/hybrid/plain | 0.9000 [0.8000, 0.9750] | 0.9000 | 0 | 36/40 | 0.0190 |
| 14 | recursive/hybrid/prefix | 0.8750 [0.7750, 0.9750] | 0.8974 | 1 | 35/39 | 0.0191 |
| 15 | recursive/hybrid/late | 0.9000 [0.8000, 0.9750] | 0.9474 | 2 | 36/38 | 0.0178 |
| 16 | recursive/rerank/plain | 0.9000 [0.8000, 0.9750] | 0.9231 | 1 | 36/39 | 0.0180 |
| 17 | recursive/rerank/prefix | 0.8500 [0.7250, 0.9500] | 0.8947 | 2 | 34/38 | 0.0178 |
| 18 | recursive/rerank/late | 0.8500 [0.7250, 0.9500] | 0.9189 | 3 | 34/37 | 0.0171 |

Baseline comparison, paired against the reference cell over the same 40 answerable items (`reports/baselines/table.md`):

| run | hit@k | cit. P | cit. R | over-abst. | ¥/1k | discordant (ref only / other only) | p |
|---|---|---|---|---|---|---|---|
| reference `…22270968` | 0.90 | 1.0000 | 0.90 | 0.025 | 9.0993 | — | — |
| closed book `…bc6b3c50` | 0.90 | 0.0000 | 0.00 | 1.000 | 0.4746 | citation 36 / 0 | 2.91e-11 |
| long context `…2b10efa0` | 0.90 | 0.0000 | 0.00 | 0.300 | 4.2440 | citation 36 / 0 | 2.91e-11 |
| all-MiniLM-L6-v2 `…e88cf6b4` | 0.65 | 0.9592 | 0.75 | 0.175 | 7.7827 | hit 13 / 3; citation 6 / 0 | 0.02127; 0.03125 |
| cheap generator `…bb87b44b` | 0.90 | 0.8704 | 0.875 | 0.025 | 4.7002 | citation 4 / 3 | 1.0000 |

Bootstrap intervals are quoted from `reports/significance.md` for citation recall, span hit rate and over-abstention only; that bundle's `hit_at_10`, `mrr` and `ndcg_at_10` rows are degenerate (§3.9), so the retrieval intervals are not reproduced here. Citation precision for the dense cell is 1.0000 over **73 claims across 35 items** (`notes/prefix-ab.md`); precision and recall have different denominators because a cell can answer one item with several claims or with none.

### A.2 Artifact index

| Artifact | Answers |
|---|---|
| `runs/<run_id>/` | One configuration: resolved config, git SHA, corpus snapshot, models, prompt hash, `predictions.jsonl`, `citations.jsonl`, `chunks.jsonl`, `metrics.json`, timings, cache stats. |
| `reports/matrix.{md,csv,json}` | The 18-cell table with the abstention working point beside each cell, main effects, interactions, digest drift, orphan runs. |
| `reports/significance.{md,csv}` | Bootstrap intervals per cell, McNemar contrasts per factor, per-stratum detail. |
| `reports/correctness.{json,csv}` | Answer correctness against the reference answer, per cell and per item. |
| `reports/chunking.{json,csv}` | The nine chunk-strategy pairs: deltas, paired tests, mechanism statistics. |
| `reports/judges.{md,csv}` | κ per verification layer and the NLI × judge confusion grid. |
| `reports/cost.{md,csv}` | Tokens by component, CNY per 1,000 questions, index size, latency. |
| `reports/abstention/*` | Precision-recall CSVs and figures for the three score scales, chosen working points with their transforms, near-miss examples at the chosen point. |
| `reports/sweeps/{k,chunk,hops}.*` | The three sensitivity curves; all ten points pending at this snapshot. |
| `reports/baselines/*` | The five baseline rows, the generator probe, the window-cost projection. |
| `notes/error-taxonomy.md` | The nine classes and every assigned failure. |
| `notes/correctness.md`, `notes/chunking-comparison.md`, `notes/prefix-ab.md`, `notes/abstention.md` | The four analysis notes the new sections are written from. |
| `notes/golden-v1-authoring.md`, `notes/prefix-audit.md`, `notes/judge-calibration.md` | Set authoring, the 20-prefix rubric audit, the 30 labelled claims. |
| `docs/adr/0001`–`0017` | The seventeen decisions this report cites. |
| `assets/report/*.png` | The three figures, redrawn from the files above by `.scratch/topic5-rag/report_figures.py`. |

### A.3 Reproduction

```bash
python -m ragqa.selftest                                    # offline test suite, no network, no GPU
python scripts/run_matrix.py                                # the 18 cells, resumable
python scripts/run_sweeps.py --emit --check                 # emit + gate the ten sweep cells
python scripts/run_sweeps.py                                # execute pending sweep points
python scripts/run_baselines.py --measure-window runs/<ref>  # window-cost.json, no model calls
python scripts/calibrate_judges.py                          # both judge layers, cached
python scripts/score_correctness.py                          # answer correctness, one call per answered item
python scripts/chunk_comparison.py                          # the nine chunk-strategy pairs
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

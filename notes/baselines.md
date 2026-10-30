# Baselines and the swaps that make the contribution arguable

Ticket 14. Four comparison cells, each a normal run directory with an id — never a
notebook, never a branch (ADR-0003). This note says what each cell isolates, what
the window actually costs, what the paired test will say, and — since the cells
have **not** produced a completed run yet — which of the four arguments is already
dead on the evidence in the tree.

Everything numeric below comes from a named artifact, and the two kinds are kept
apart: **measured** means a run directory or a live API response; **projected**
means arithmetic over a measured run and the corpus.

| source | kind | what it holds |
|---|---|---|
| `runs/real-llm-20261030T113604-a5c0a3e4` | measured | the reference pipeline on golden **v0** (20 items, 10 answerable), deepseek-v4.1-flash, hit@10 = 1.000, ¥10.1184 per 1,000 questions |
| `runs/real-rerank-20261030T095541-a6eb2d5e` | measured | the same retrieval with the stub generator; used only to smoke-test the table on real artifacts |
| `reports/baselines/window-cost.json` | projected | prompt shapes and their token/¥ cost, built from that run plus the corpus by `scripts/run_baselines.py --measure-window` (regenerate it rather than trusting this copy) |
| `reports/baselines/generator-probe.json` | measured | the generator probe: live price per model, contract pass/fail, USD per question on this workload |
| `reports/baselines/model-catalog-2026-10-30.json` | measured | the gateway's own price list, as fetched |
| `data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl` | measured | the corpus the document-length distribution is measured on |

## Status: verified, not run

`golden/v1.jsonl` is on the branch now (60 items, 40 answerable) and the four
cells plus the reference are `--dry-run` verified against it. No cell has a
completed run, so `reports/baselines/table.{md,json}` is deliberately absent: a
table with no runs in it would be a lie about what was measured.

Two attempts are worth recording rather than hiding. The first was blocked by the
ticket's own dependency — v1 landed late — and the second was stopped on purpose:
the run started while the 18-cell matrix owned the GPU, and with both resident a
6 GB card sat at 5.8 / 6.1 GB while the matrix cell crawled. The matrix is the
report's headline evidence and it goes first. Anything that embeds 2,203 chunks
and then answers 300 questions needs the card to itself.

The dry run against the real set:

```
cell               config                                                    items   ans   calls  state
baseline-reference configs/ctx-plain.yaml (retargeted at the baselines' golden set)  60    40      60  pending
closed-book        configs/baselines/closed-book.yaml                           60    40      60  pending
long-context       configs/baselines/long-context.yaml                          60    40      60  pending
embed-minilm       configs/baselines/embed-minilm.yaml                          60    40      60  pending
gen-cheap          configs/baselines/gen-cheap.yaml                             60    40      60  pending

Projected generation calls: 300 (5 cells x items)
```

So, precisely: the corpus distribution, the prompt-shape costs, the model catalog
and the generator probe in this note are **measured**; the four cells' retrieval,
citation, abstention, latency and cost columns, and every McNemar number, are
**pending** and will be filled by

```bash
python scripts/run_baselines.py --with-reference
python scripts/run_baselines.py --report --reference-dir runs/<baseline-reference-run-id>
```

`--with-reference` is opt-in and exists for exactly this reason: the four cells
must be paired against a cell that answered the same items, and
`configs/ctx-plain.yaml` still points at golden v0. The flag derives that
configuration with a new run name and the baselines' golden set — identity keys
only, asserted in `tests/test_baselines.py` — so the headline comparison cannot
quietly acquire a second factor. Without the flag the runner executes exactly the
four baselines and nothing else.


## The four cells

Each differs from `configs/ctx-plain.yaml` in exactly one factor, and the table
prints that factor list per row rather than trusting the author:

| cell | config | the factor | what it isolates | deliberately not changed |
|---|---|---|---|---|
| closed book | `configs/baselines/closed-book.yaml` | `baseline.closed_book` | what the whole retrieval + context pipeline buys, with the generator and prompt held fixed | generator, prompt, chunking, index, golden set |
| long context | `configs/baselines/long-context.yaml` | `baseline.long_context`, `baseline.long_context_max_chars: 20000` | retrieval-as-selection versus retrieval-as-compression | generator, prompt, embedding, k |
| smaller embedder | `configs/baselines/embed-minilm.yaml` | `embed.model_id`, `embed.max_seq_length`, `retrieval.mode: dense` | the first-stage dense retrieval a 384-dim / 256-token model produces | generator, prompt, chunks, index backend, k |
| cheaper generator | `configs/baselines/gen-cheap.yaml` | `llm.model_generate`, the two prices | the reader alone | retrieval at full strength, prompt, context budget |

`ragqa.baselines.substantive_diff` reports the keys that moved and
`differing_factors` groups them into declared factors, so "exactly one factor" is
checked per table instead of asserted in prose. Identity keys (`run.name`,
`run.out_root`, `golden.items_path`, `golden.limit`) are ignored: they name a cell
and its instrument, they do not change behaviour.

## Closed book says less than it looks like it says

`baseline.closed_book` empties the retrieval block and leaves everything else
alone, which is what makes it a clean contrast. It also makes the result
**uninterpretable as a knowledge test**, and the note has to say so before the
number reaches the report.

The shared system prompt (`ragqa/generate.py:SYSTEM_PROMPT`) instructs the model to
answer "using ONLY the numbered context chunks provided", to "never use outside
knowledge", and to set `answerable: false` when the context does not contain the
answer. With the block emptied, a compliant model abstains on almost everything.
So the closed-book cell measures *what the context block buys under this prompt*,
which is exactly the quantity the report needs — and it does **not** measure what
the model knows about Vault from pre-training. "Closed book scores 0.05, therefore
the model knows nothing" would be a false claim about the model; the true claim is
"with the grounding instruction in force and no context, the system declines".

Retrieval still executes in this cell, on purpose: hit@k is printed next to
correctness so a lucky closed-book answer on a question whose evidence was
retrieved anyway cannot be read as evidence that the index was unnecessary.

## Long context: what the window costs

The cap is a measured choice. Corpus, 1,268 documents, 5,622,957 characters:

| statistic | chars |
|---|---|
| median | 1,573 |
| mean | 4,434.5 |
| p90 | 10,985 |
| p95 | 16,677 |
| p99 | 33,231 |
| max | 195,456 (`api-docs/secret/pki`) |

What decides the cap is not that distribution but the documents this cell will
actually paste: the top-ranked document of each golden item. On the 20 golden v0
items those run to 60,945 chars at the extreme, and on the **answerable** items
they top out at **19,391 chars** (`window-cost.json:top_doc_chars`). The config
sets 20,000: the smallest round number that holds every answerable item's document
whole, so the cell cannot lose an answer inside its own truncation. It also holds
19 of the 20 documents overall; the one it cuts belongs to a near-miss.

Cost, at deepseek-v4.1-flash's $0.15 / $0.60 per Mtok, on those 20 items:

| prompt shape | prompt chars (mean) | prompt tokens (mean) | ¥ per 1,000 questions | documents whole |
|---|---|---|---|---|
| retrieval, k=10, 8 chunks pasted | 27,654 | 6,897 | 9.54 | – |
| closed book, empty block | 756 | 189 | 2.82 | – |
| long context, 12,000 cap | 7,571 | 1,888 | 4.52 | 16/20 |
| **long context, 20,000 cap** | **8,546** | **2,131** | **4.77** | **19/20** |
| long context, 70,000 cap (everything whole) | 10,593 | 2,642 | 5.28 | 20/20 |

The projection is a ratio, not a curve fit: the prompt text for every shape is
built by the real `LLMGenerator._messages`, and `tokens = chars x 0.2494`, the
median tokens-per-char of the run that measured 20 real prompts (4.009 chars per
token). It reproduces the measured RAG prompt to within 8% (6,897 projected
against 7,479 measured), and that 8% is the error bar to carry on the other rows.
Two items (`A002`, `A009`) are excluded from the rate because their `tokens_in`
covers the corrective retry in `generate.py`, not a longer prompt; including them
would have inflated every projection by ~10%.

**The window is the cheaper cell, not the expensive one.** The reference cell pastes
eight chunks averaging 3.4 k chars each — 27,654 chars — while one document capped
at 20,000 chars pastes a third of that in tokens. Raising the cap does not rescue
the intuition: the 70,000 row is the *no-truncation* case (it holds all 20
documents), and even there the prompt averages 2,642 tokens, 38% of the reference
cell's 6,897. The reason is structural — this corpus's documents are short (mean
4,435 chars) and the reference cell pastes eight of them at once. Long context
would only become the expensive cell on a corpus of long documents, or with more
than about eight chunks pasted. So the obvious argument against it ("it costs too
much per question") is measurably false here, and the report must not make it.
Note also that the RAG prompt holds 8 chunks while recall is measured at k=10:
`llm.context_chunks` is 8, so two of the ten retrieved chunks never reach the
model.

## Long context: what the window buys

Three things, and only one of them is free:

1. **Contiguity.** A 512-word chunk boundary cuts through code blocks, tables and
   option lists. A fact that straddles the seam is invisible to a chunk-level
   retriever and present in the document.
2. **Recall at the document level.** The retrieval step shrinks from "top 10 chunks"
   to "top 1 document", so evidence that sits in the right document but the wrong
   chunk becomes reachable. Given that the reference cell's hit@10 is already 1.000
   on golden v0 (`real-llm-...113604`), this buys nothing there — it is a bet that
   v1's harder items are the ones where chunking hurts.
3. **A broken citation handle.** This is the cost the money column hides. The
   prompt for this cell contains no chunk ids — there are none to contain — so a
   claim comes back citing a document id. `verify.check_claims` looks that id up in
   the retrieved chunks, does not find it, and records `chunk_not_retrieved`;
   `generate.py` files the claim under `doc_id: ""`. Expected signature in the
   table: **citation precision 0, `no-cite` unchanged (the claims exist, they are
   just unsupported), and `over-abstain` set by the model's own judgement** rather
   than by any verifier. If the run shows anything else, the reasoning above is
   wrong and the note has to be rewritten.

## The embedding swap

`all-MiniLM-L6-v2` is 384-dim and 256 positions against bge-m3's 1,024 dimensions
and 8 k window — the model you reach for when the GPU budget is a laptop. Two keys
move with it and both are consequences rather than extra variables:
`embed.max_seq_length: 256`, because `ragqa/embed.py` assigns `max_seq_length` to
the sentence-transformer verbatim and MiniLM has no positions beyond 256; and
`retrieval.mode: dense`, because the cross-encoder is precisely the component that
repairs a weak first stage. Leaving the reranker on would produce "the embedding
model does not matter" while a 568 M-parameter re-ranker did the work over the top
12 candidates. The cell is defined as the dense stage alone, and ADR-0011 still
holds: k=10 with no rerank means the dense stage returns all 10 candidates, so
hit@10 measures retrieval rather than truncation.

## The generator swap

"Cheapest working" was probed, not guessed. Every model with an input price at or
below $0.15 was asked one miniature version of this project's own task — same
system prompt, one context chunk, same JSON contract, `max_tokens: 900` — and
scored on whether the contract came back and what a question would cost at *this*
workload's token mix (7,479 prompt + 659 completion tokens, measured on
`real-llm-...113604`). Total probe spend across all 19 requests: $0.0017.

| model | price / Mtok | USD per question | verdict |
|---|---|---|---|
| beam-free | 0.00 / 0.00 | 0.000000 | passed; excluded, see below |
| muse-spark-1.2-contributor | 0.10 / 0.20 | 0.000821 | passed, but spent 908‰ of the output budget on one sentence |
| claude-haiku-5-5 | 0.10 / 0.50 | 0.001019 | passed |
| **gpt-6-luna** | **0.10 / 0.50** | **0.001019** | **passed; chosen** |
| mimo-v2.6-flash | 0.14 / 0.28 | 0.001150 | passed |
| qwen3.8-flash | 0.15 / 0.47 | 0.001344 | passed |
| glm-5.3-flash | 0.15 / 0.50 | 0.001364 | passed |
| deepseek-v4.1-flash | 0.15 / 0.60 | 0.001430 | the reference cell |
| minimax-m3.1-flash | 0.15 / 0.60 | 0.001430 | passed |
| muse-spark-1.3-contributor | 0.10 / 0.20 | — | failed: empty content, then timeout |
| hy3 | 0.14 / 0.58 | — | failed: upstream 400 |

Three lessons that belong in the report's cost paragraph. Input price decides 91%
of this mix, so a cheaper *output* price alone does not make a model cheaper here
(mimo at $0.14 / $0.28 loses to luna at $0.10 / $0.50). A low sticker price can
hide a generator that thinks out loud: muse-spark-1.3 has the cheapest list price
in the catalog and returned nothing but reasoning tokens. And the win is modest —
$0.001019 against $0.001430 per question, ¥6.80 against ¥9.54 per 1,000, a 29%
saving, which is a reasonable business claim and not a headline.

`beam-free` is listed at $0.00 / $0.00 and passed the same probe. It is excluded
because a zero price collapses the cost axis this cell exists to move, and a
promotional free tier is not a price the project can plan on. It is one line away
in the config, and its probe result is in the evidence file so the choice can be
disputed with data.

## Paired significance

Both cells answer the identical items, so outcomes are paired by `item_id` and
McNemar's test uses only the discordant pairs — items both cells got right, or both
got wrong, say nothing about a difference. Two metrics are tested:

- **citation support** — item has at least one claim whose citation passed the
  containment layer. This is the headline, because it is what "verifiable
  citations" means: right answer, wrong evidence is a failure here.
- **retrieval hit@k** — item's evidence quote was found in the top k chunks, where
  applicable. Closed book and long context still retrieve, so this row isolates
  whether a cell changed retrieval or only what was shown to the generator.

The arithmetic is `ragqa.baselines.mcnemar_counts`, tested against hand-computed
2×2 tables in `tests/test_baselines.py`: exact conditional binomial at or below 25
discordant pairs, continuity-corrected chi-square above it, and the discordant
counts are printed next to p so a reader can check the test was applied to
something. Worked example from the closed-book fixture: 5 discordant pairs all
against the baseline gives p = 2·C(5,0)/2⁵ = 0.0625 — *not* significant at 0.05,
which is the honest outcome for ten answerable items and precisely why ADR-0005
insists on 40. At 40 answerable items, 6:0 gives p = 2/2⁶ = 0.031 and clears the
threshold while 5:0 still does not: that is the smallest unanimous difference the
set can detect, and detectability of differences that size is what the set size
buys.

The numbers themselves are not in this note yet, on purpose. Hand-writing a
2×2 for a run that has not happened is exactly how a note ends up disagreeing
with its own run directory; the table prints the counts when the cells run, and
`mcnemar_counts` is the only place the p-values come from.

## Honest verdict, as far as the evidence goes today

1. **One argument is already dead.** Long context is not the expensive baseline:
   a projected 2,131 prompt tokens per question against the reference cell's 6,897,
   ¥4.77 against ¥9.54 per 1,000 (`window-cost.json`), and the no-truncation row is
   still only 2,642. Those are projections with an 8% error bar, but the gap is
   3× — an error bar cannot close it. If the report claims RAG wins on cost, its
   own table will contradict it. What long context really costs is the citation
   handle.
2. **The headline comparison may be uninformative by construction.** Closed book
   under this prompt should abstain on nearly everything, so RAG-versus-no-RAG on
   citation support should come out overwhelming (of the order of 5:0 to 9:0
   discordant) for a reason that is a property of the prompt, not of retrieval.
   That is a prediction, not a result, and it is the first thing to check when the
   run lands. It is still worth running — it bounds what the context block buys and
   it is the number a reader expects — but the *interesting* baselines are the other
   three.
3. **What a baseline win would mean.** If `embed-minilm` ties on hit@10, the
   1,024-dimension model is unearned and the report should say so, because that is
   a 5× cheaper index for the same recall. If `gen-cheap` ties on citation
   precision, the expensive reader is unearned and the 29% is free money. If
   `long-context` beats RAG on answer correctness while losing citation precision,
   the finding is not "retrieval is unnecessary" but "the chunk-level citation
   contract is what retrieval costs" — and the fix is a claim-to-document
   verification layer, not a bigger window.
4. **A baseline winning is a result, not a failure.** The matrix exists to find out
   which mechanism is carrying the system. Nothing here is written to protect the
   pipeline; ADR-0003's ceteris paribus rule and the paired test are the two things
   that make an inconvenient answer publishable.

## Regenerate

```bash
python scripts/run_baselines.py --dry-run                            # plan, a count, zero spend
python scripts/run_baselines.py --measure-window runs/<ref-run-id>   # window-cost.json, no model calls
python scripts/run_baselines.py --with-reference                     # 5 cells x 60 items, GPU to itself
python scripts/run_baselines.py --report --reference-dir runs/<baseline-reference-run-id>
python -m ragqa.selftest                                             # 155 tests
```

The run order inside `--with-reference` matters on a shared card: the reference
cell goes first so a failure there costs one cell rather than five, and
`embed-minilm` goes third so the 384-dimension collection it builds is replaced by
a 1,024-dimension one before the last cell finishes. Every cell rebuilds its
collection anyway (`QdrantIndex.add` deletes and recreates), so a run is never
reading another run's vectors.

`--report` writes `reports/baselines/table.md` and `table.json`: one row per
configuration (run id, hit@k, citation precision/recall for the containment layer
and the NLI/judge layers when they judged, over-abstain rate, p50/p95, prompt and
completion tokens, ¥ per 1,000 questions, answers with no citation), the paired
McNemar rows with their discordant counts, and the per-row factor diff that says
whether the comparison is single-variable.

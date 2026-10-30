# Baseline comparison

Reference cell: `baseline-reference-20261030T175101-22270968`

| run | hit@k | cit P | cit R | NLI P | judge P | over-abst | p50 ms | p95 ms | tok in | tok out | CNY/1k | no-cite | factors vs ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline-reference-20261030T175101-22270968 | 0.9 | 1 | 0.9 | - | - | 0.025 | 3634 | 20373 | 404279 | 35351 | 9.099 | 3 | - |
| baseline-closed-book-20261030T180238-bc6b3c50 | 0.9 | 0 | 0 | - | - | 1 | 5086 | 6554 | 12207 | 4063 | 0.4746 | 0 | baseline-policy |
| baseline-long-context-20261030T180847-2b10efa0 | 0.9 | 0 | 0 | - | - | 0.3 | 4097 | 10430 | 149974 | 26135 | 4.244 | 0 | baseline-policy |
| baseline-embed-minilm-20261030T181714-e88cf6b4 | 0.65 | 0.9592 | 0.75 | - | - | 0.175 | 5120 | 14932 | 329671 | 34264 | 7.783 | 2 | embedder, retrieval-mode |
| baseline-gen-cheap-20261030T182501-bb87b44b | 0.9 | 0.8704 | 0.875 | - | - | 0.025 | 4466 | 6964 | 368590 | 10843 | 4.7 | 0 | generator-model |

`hit@k` is retrieval hit rate on answerable items; `cit P` / `cit R` are the containment layer's citation precision and item-level recall; `NLI P` and `judge P` are only filled when that layer judged claims; `over-abst` is the rate at which answerable items were refused; `no-cite` counts answers that name no citation at all.

## Paired significance

Both configurations answer the identical golden items, so outcomes are paired by `item_id`. McNemar's test uses only the discordant pairs; the exact conditional binomial is used at or below 25 discordant pairs, the continuity-corrected chi-square above it.

| metric | run vs reference | paired items | baseline only | treatment only | statistic | p | method |
|---|---|---|---|---|---|---|---|
| citation_support | baseline-closed-book-20261030T180238-bc6b3c50 | 40 | 36 | 0 | 34.03 | 2.91e-11 | exact_binomial |
| retrieval_hit | baseline-closed-book-20261030T180238-bc6b3c50 | 40 | 0 | 0 | 0 | 1 | exact_binomial |
| citation_support | baseline-long-context-20261030T180847-2b10efa0 | 40 | 36 | 0 | 34.03 | 2.91e-11 | exact_binomial |
| retrieval_hit | baseline-long-context-20261030T180847-2b10efa0 | 40 | 0 | 0 | 0 | 1 | exact_binomial |
| citation_support | baseline-embed-minilm-20261030T181714-e88cf6b4 | 40 | 6 | 0 | 4.167 | 0.03125 | exact_binomial |
| retrieval_hit | baseline-embed-minilm-20261030T181714-e88cf6b4 | 40 | 13 | 3 | 5.062 | 0.02127 | exact_binomial |
| citation_support | baseline-gen-cheap-20261030T182501-bb87b44b | 40 | 4 | 3 | 0 | 1 | exact_binomial |
| retrieval_hit | baseline-gen-cheap-20261030T182501-bb87b44b | 40 | 0 | 0 | 0 | 1 | exact_binomial |

`baseline only` counts items the reference got right and the other cell got wrong; `treatment only` is the reverse. A claim of improvement needs the treatment-only side to dominate *and* p below 0.05.

## Ceteris paribus

- `baseline-reference-20261030T175101-22270968`: reference cell.
- `baseline-closed-book-20261030T180238-bc6b3c50`: one factor (baseline-policy); keys: `baseline.closed_book`.
- `baseline-long-context-20261030T180847-2b10efa0`: one factor (baseline-policy); keys: `baseline.long_context`, `baseline.long_context_max_chars`.
- `baseline-embed-minilm-20261030T181714-e88cf6b4`: MORE THAN ONE FACTOR (embedder, retrieval-mode); keys: `embed.max_seq_length`, `embed.model_id`, `retrieval.mode`.
- `baseline-gen-cheap-20261030T182501-bb87b44b`: one factor (generator-model); keys: `llm.model_generate`, `llm.price_in_usd_per_mtok`, `llm.price_out_usd_per_mtok`.

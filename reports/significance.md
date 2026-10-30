# Paired significance and intervals

- resample unit: **item** (a golden question, not a claim); claims travel with their item because they are not independent of it
- bootstrap: 10000 resamples, seed 20261030 (per cell: seed XOR crc32(cell)), percentile interval, 95% confidence
- paired test: McNemar's exact test on discordant pairs, two-sided exact binomial
- the seed is fixed per cell as `20261030 XOR crc32(cell)`; a cell added later does not move another cell's interval

## Interval per cell and headline metric

| cell | run id | hit@10 [95% CI] | MRR [95% CI] | nDCG@10 [95% CI] | cit. prec. [95% CI] | cit. rec. [95% CI] | span hit [95% CI] | over-abst. [95% CI] | abst. rec. [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| cell-fixed-dense-plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 0.8500 [0.7250, 0.9500] | 0.4817 [0.3669, 0.5986] | 0.5697 [0.4626, 0.6740] | 1.0000 [1.0000, 1.0000] | 0.8750 [0.7750, 0.9750] | 1.0000 [1.0000, 1.0000] | 0.1000 [0.0250, 0.2000] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-dense-contextual_prefix | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | 0.8250 [0.7000, 0.9250] | 0.4180 [0.3061, 0.5344] | 0.5145 [0.4082, 0.6202] | 0.9818 [0.9400, 1.0000] | 0.8000 [0.6750, 0.9250] | 0.9818 [0.9400, 1.0000] | 0.1500 [0.0500, 0.2750] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-hybrid-plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 0.9000 [0.8000, 0.9750] | 0.6529 [0.5458, 0.7562] | 0.7163 [0.6170, 0.8083] | 0.9846 [0.9524, 1.0000] | 0.9500 [0.8750, 1.0000] | 0.9846 [0.9524, 1.0000] | 0.0500 [0.0000, 0.1250] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-hybrid-contextual_prefix | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | 0.8750 [0.7750, 0.9750] | 0.5737 [0.4654, 0.6821] | 0.6503 [0.5474, 0.7464] | 0.9844 [0.9508, 1.0000] | 0.9000 [0.8000, 0.9750] | 0.9844 [0.9508, 1.0000] | 0.0500 [0.0000, 0.1250] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-plain | grid-fixed-rerank-plain-20261030T125648-57be667d | 0.9000 [0.8000, 0.9750] | 0.6044 [0.4743, 0.7300] | 0.6743 [0.5606, 0.7821] | 0.9206 [0.8136, 1.0000] | 0.8750 [0.7750, 0.9750] | 0.9206 [0.8136, 1.0000] | 0.0250 [0.0000, 0.0750] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-rerank-contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | 0.8750 [0.7750, 0.9750] | 0.6184 [0.4885, 0.7483] | 0.6786 [0.5627, 0.7927] | 0.9500 [0.8625, 1.0000] | 0.9500 [0.8750, 1.0000] | 0.9500 [0.8625, 1.0000] | 0.0250 [0.0000, 0.0750] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-plain | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | 0.8500 [0.7250, 0.9500] | 0.4792 [0.3635, 0.5968] | 0.5681 [0.4605, 0.6734] | 0.9577 [0.9041, 1.0000] | 0.9000 [0.8000, 0.9750] | 0.9577 [0.9041, 1.0000] | 0.0500 [0.0000, 0.1250] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-dense-contextual_prefix | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | 0.8750 [0.7750, 0.9750] | 0.5045 [0.3846, 0.6261] | 0.5920 [0.4844, 0.6980] | 1.0000 [1.0000, 1.0000] | 0.9750 [0.9250, 1.0000] | 1.0000 [1.0000, 1.0000] | 0.0250 [0.0000, 0.0750] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-plain | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 0.9000 [0.8000, 0.9750] | 0.6521 [0.5396, 0.7604] | 0.7152 [0.6120, 0.8087] | 0.9571 [0.9103, 1.0000] | 1.0000 [1.0000, 1.0000] | 0.9571 [0.9103, 1.0000] | 0.0000 [0.0000, 0.0000] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-hybrid-contextual_prefix | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | 0.9000 [0.8000, 0.9750] | 0.6432 [0.5315, 0.7515] | 0.7084 [0.6058, 0.8027] | 0.9753 [0.9390, 1.0000] | 0.9750 [0.9250, 1.0000] | 0.9753 [0.9390, 1.0000] | 0.0250 [0.0000, 0.0750] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | 0.9000 [0.8000, 0.9750] | 0.5985 [0.4775, 0.7198] | 0.6707 [0.5633, 0.7762] | 1.0000 [1.0000, 1.0000] | 0.9000 [0.8000, 0.9750] | 1.0000 [1.0000, 1.0000] | 0.0250 [0.0000, 0.0750] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-rerank-contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | 0.9000 [0.8000, 0.9750] | 0.5880 [0.4647, 0.7138] | 0.6621 [0.5532, 0.7703] | 0.9516 [0.8750, 1.0000] | 0.8500 [0.7250, 0.9500] | 0.9516 [0.8750, 1.0000] | 0.0500 [0.0000, 0.1250] | 1.0000 [1.0000, 1.0000] |
| cell-recursive_parent_child-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |

## Factor contrasts

One pair of cells per stratum of the other two factors; discordant pairs are pooled within a contrast. `b` counts items only the treated level got right, `c` only the reference level. `p` is exact, not asymptotic.

| contrast | outcome | strata | pairs | b | c | p | winner |
|---|---|---|---|---|---|---|---|
| rerank vs hybrid (retrieval) | retrieval_hit | 4 | 160 | 0 | 0 | 1.000000 | tie |
| rerank vs hybrid (retrieval) | grounded_citation | 4 | 160 | 5 | 15 | 0.041389 | hybrid |
| rerank vs hybrid (retrieval) | abstention_decision | 4 | 240 | 4 | 4 | 1.000000 | tie |
| contextual_prefix vs plain (contextualization) | retrieval_hit | 6 | 240 | 3 | 5 | 0.726562 | plain |
| contextual_prefix vs plain (contextualization) | grounded_citation | 6 | 240 | 9 | 11 | 0.823803 | plain |
| contextual_prefix vs plain (contextualization) | abstention_decision | 6 | 360 | 5 | 8 | 0.581055 | plain |
| late_chunking vs plain (contextualization) | retrieval_hit | 0 | 0 | 0 | 0 | missing | missing |
| late_chunking vs plain (contextualization) | grounded_citation | 0 | 0 | 0 | 0 | missing | missing |
| late_chunking vs plain (contextualization) | abstention_decision | 0 | 0 | 0 | 0 | missing | missing |

A contrast with no paired cells prints `missing`: the matrix had not finished both ends of it when this bundle was generated, and inventing a zero would look like evidence of no difference.

## Per-stratum detail

| contrast | outcome | stratum | left run | right run | pairs | b | c | p |
|---|---|---|---|---|---|---|---|---|
| rerank vs hybrid (retrieval) | retrieval_hit | chunk_strategy,context_mode=fixed/contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | 40 | 0 | 0 | 1.000000 |
| rerank vs hybrid (retrieval) | retrieval_hit | chunk_strategy,context_mode=fixed/plain | grid-fixed-rerank-plain-20261030T125648-57be667d | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 40 | 0 | 0 | 1.000000 |
| rerank vs hybrid (retrieval) | retrieval_hit | chunk_strategy,context_mode=recursive_parent_child/contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | 40 | 0 | 0 | 1.000000 |
| rerank vs hybrid (retrieval) | retrieval_hit | chunk_strategy,context_mode=recursive_parent_child/plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 40 | 0 | 0 | 1.000000 |
| rerank vs hybrid (retrieval) | grounded_citation | chunk_strategy,context_mode=fixed/contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | 40 | 4 | 2 | 0.687500 |
| rerank vs hybrid (retrieval) | grounded_citation | chunk_strategy,context_mode=fixed/plain | grid-fixed-rerank-plain-20261030T125648-57be667d | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 40 | 0 | 3 | 0.250000 |
| rerank vs hybrid (retrieval) | grounded_citation | chunk_strategy,context_mode=recursive_parent_child/contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | 40 | 1 | 6 | 0.125000 |
| rerank vs hybrid (retrieval) | grounded_citation | chunk_strategy,context_mode=recursive_parent_child/plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 40 | 0 | 4 | 0.125000 |
| rerank vs hybrid (retrieval) | abstention_decision | chunk_strategy,context_mode=fixed/contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | 60 | 2 | 1 | 1.000000 |
| rerank vs hybrid (retrieval) | abstention_decision | chunk_strategy,context_mode=fixed/plain | grid-fixed-rerank-plain-20261030T125648-57be667d | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 60 | 1 | 0 | 1.000000 |
| rerank vs hybrid (retrieval) | abstention_decision | chunk_strategy,context_mode=recursive_parent_child/contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | 60 | 1 | 2 | 1.000000 |
| rerank vs hybrid (retrieval) | abstention_decision | chunk_strategy,context_mode=recursive_parent_child/plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 60 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=fixed/dense | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 40 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=fixed/hybrid | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 40 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=fixed/rerank | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-rerank-plain-20261030T125648-57be667d | 40 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=recursive_parent_child/dense | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | 40 | 3 | 2 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=recursive_parent_child/hybrid | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 40 | 0 | 0 | 1.000000 |
| contextual_prefix vs plain (contextualization) | retrieval_hit | chunk_strategy,retrieval_mode=recursive_parent_child/rerank | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | 40 | 0 | 0 | 1.000000 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=fixed/dense | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 40 | 2 | 5 | 0.453125 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=fixed/hybrid | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 40 | 0 | 2 | 0.500000 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=fixed/rerank | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-rerank-plain-20261030T125648-57be667d | 40 | 4 | 1 | 0.375000 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=recursive_parent_child/dense | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | 40 | 3 | 0 | 0.250000 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=recursive_parent_child/hybrid | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 40 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | grounded_citation | chunk_strategy,retrieval_mode=recursive_parent_child/rerank | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | 40 | 0 | 2 | 0.500000 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=fixed/dense | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 60 | 2 | 4 | 0.687500 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=fixed/hybrid | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 60 | 1 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=fixed/rerank | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | grid-fixed-rerank-plain-20261030T125648-57be667d | 60 | 1 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=recursive_parent_child/dense | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | 60 | 1 | 0 | 1.000000 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=recursive_parent_child/hybrid | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 60 | 0 | 1 | 1.000000 |
| contextual_prefix vs plain (contextualization) | abstention_decision | chunk_strategy,retrieval_mode=recursive_parent_child/rerank | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | 60 | 0 | 1 | 1.000000 |


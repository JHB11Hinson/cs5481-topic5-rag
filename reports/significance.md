# Paired significance and intervals

- resample unit: **item** (a golden question, not a claim); claims travel with their item because they are not independent of it
- bootstrap: 10000 resamples, seed 20261030 (per cell: seed XOR crc32(cell)), percentile interval, 95% confidence
- paired test: McNemar's exact test on discordant pairs, two-sided exact binomial
- the seed is fixed per cell as `20261030 XOR crc32(cell)`; a cell added later does not move another cell's interval

## Interval per cell and headline metric

| cell | run id | hit@10 [95% CI] | MRR [95% CI] | nDCG@10 [95% CI] | cit. prec. [95% CI] | cit. rec. [95% CI] | span hit [95% CI] | over-abst. [95% CI] | abst. rec. [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| cell-fixed-dense-plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 0.8500 [0.7250, 0.9500] | 0.4817 [0.3669, 0.5986] | 0.5697 [0.4626, 0.6740] | 1.0000 [1.0000, 1.0000] | 0.8750 [0.7750, 0.9750] | 1.0000 [1.0000, 1.0000] | 0.1000 [0.0250, 0.2000] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-dense-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-hybrid-plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 0.9000 [0.8000, 0.9750] | 0.6529 [0.5458, 0.7562] | 0.7163 [0.6170, 0.8083] | 0.9846 [0.9524, 1.0000] | 0.9500 [0.8750, 1.0000] | 0.9846 [0.9524, 1.0000] | 0.0500 [0.0000, 0.1250] | 1.0000 [1.0000, 1.0000] |
| cell-fixed-hybrid-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing |

## Factor contrasts

One pair of cells per stratum of the other two factors; discordant pairs are pooled within a contrast. `b` counts items only the treated level got right, `c` only the reference level. `p` is exact, not asymptotic.

| contrast | outcome | strata | pairs | b | c | p | winner |
|---|---|---|---|---|---|---|---|
| rerank vs hybrid (retrieval) | retrieval_hit | 0 | 0 | 0 | 0 | missing | missing |
| rerank vs hybrid (retrieval) | grounded_citation | 0 | 0 | 0 | 0 | missing | missing |
| rerank vs hybrid (retrieval) | abstention_decision | 0 | 0 | 0 | 0 | missing | missing |
| contextual_prefix vs plain (contextualization) | retrieval_hit | 0 | 0 | 0 | 0 | missing | missing |
| contextual_prefix vs plain (contextualization) | grounded_citation | 0 | 0 | 0 | 0 | missing | missing |
| contextual_prefix vs plain (contextualization) | abstention_decision | 0 | 0 | 0 | 0 | missing | missing |
| late_chunking vs plain (contextualization) | retrieval_hit | 0 | 0 | 0 | 0 | missing | missing |
| late_chunking vs plain (contextualization) | grounded_citation | 0 | 0 | 0 | 0 | missing | missing |
| late_chunking vs plain (contextualization) | abstention_decision | 0 | 0 | 0 | 0 | missing | missing |

A contrast with no paired cells prints `missing`: the matrix had not finished both ends of it when this bundle was generated, and inventing a zero would look like evidence of no difference.

## Per-stratum detail

| contrast | outcome | stratum | left run | right run | pairs | b | c | p |
|---|---|---|---|---|---|---|---|---|


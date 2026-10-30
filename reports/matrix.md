# The 18-cell matrix

Every row is one declared cell. `missing` means the cell produced no run that could be read: it is printed, never dropped, so the table always has the design's row count.

- runs root: `D:\DE Project\wt\exp\runs`
- cells: 18 declared, 2 finished, 1 unfinished, 0 unreadable, 15 absent
- joined by recomputed config digest, never by timestamp; 18 cell(s) carry a stale digest in `grid.json` (see `matrix.json`)
- `abst. t` is the cell's own `generate.abstain_score_threshold`; it differs per retrieval level because each level is scored on its own scale

| # | cell | chunk | retrieval | context | run id | items | abst. t | hit@10 | MRR | nDCG@10 | cit. prec. | cit. rec. | span hit | over-abst. | abst. rec. | p50 ms | p95 ms | CNY/1k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | cell-fixed-dense-plain | fixed | dense | plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 60 | 0.2000 | 0.8500 | 0.4817 | 0.5697 | 1.0000 | 0.8750 | 1.0000 | 0.1000 | 1.0000 | 17.3 | 21.3 | 9.2745 |
| 2 | cell-fixed-dense-contextual_prefix | fixed | dense | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 3 | cell-fixed-dense-late_chunking | fixed | dense | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 4 | cell-fixed-hybrid-plain | fixed | hybrid | plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 60 | 0.0100 | 0.9000 | 0.6529 | 0.7163 | 0.9846 | 0.9500 | 0.9846 | 0.0500 | 1.0000 | 39.9 | 7502.5 | 8.4638 |
| 5 | cell-fixed-hybrid-contextual_prefix | fixed | hybrid | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 6 | cell-fixed-hybrid-late_chunking | fixed | hybrid | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 7 | cell-fixed-rerank-plain | fixed | rerank | plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 8 | cell-fixed-rerank-contextual_prefix | fixed | rerank | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 9 | cell-fixed-rerank-late_chunking | fixed | rerank | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 10 | cell-recursive_parent_child-dense-plain | recursive_parent_child | dense | plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 11 | cell-recursive_parent_child-dense-contextual_prefix | recursive_parent_child | dense | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 12 | cell-recursive_parent_child-dense-late_chunking | recursive_parent_child | dense | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 13 | cell-recursive_parent_child-hybrid-plain | recursive_parent_child | hybrid | plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 14 | cell-recursive_parent_child-hybrid-contextual_prefix | recursive_parent_child | hybrid | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 15 | cell-recursive_parent_child-hybrid-late_chunking | recursive_parent_child | hybrid | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 16 | cell-recursive_parent_child-rerank-plain | recursive_parent_child | rerank | plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 17 | cell-recursive_parent_child-rerank-contextual_prefix | recursive_parent_child | rerank | contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 18 | cell-recursive_parent_child-rerank-late_chunking | recursive_parent_child | rerank | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |

## Main effects

Each mean is over the cells that finished with a non-missing value; the cell count travels beside it, because a level resting on one cell is not the same claim as a level resting on six.

**chunk strategy — hit@10** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| fixed | 0.8750 | 2 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| recursive_parent_child | missing | 0 | missing |

**chunk strategy — citation precision** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| fixed | 0.9923 | 2 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| recursive_parent_child | missing | 0 | missing |

**retrieval — hit@10** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| dense | 0.8500 | 1 | grid-fixed-dense-plain-20261030T124637-8ae4eb06 |
| hybrid | 0.9000 | 1 | grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| rerank | missing | 0 | missing |

**retrieval — citation precision** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| dense | 1.0000 | 1 | grid-fixed-dense-plain-20261030T124637-8ae4eb06 |
| hybrid | 0.9846 | 1 | grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| rerank | missing | 0 | missing |

**contextualization — hit@10** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| plain | 0.8750 | 2 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| contextual_prefix | missing | 0 | missing |
| late_chunking | missing | 0 | missing |

**contextualization — citation precision** (over 2 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| plain | 0.9923 | 2 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66 |
| contextual_prefix | missing | 0 | missing |
| late_chunking | missing | 0 | missing |

## Interactions

The term is `mean(i,j) - mean(i) - mean(j) + grand mean`: zero when the two factors add up on this metric, and the sign says which corner beats the additive prediction.

**Read this as unestimated, not as zero.** Only 2 corners of the 2 x 3 x 3 design have a finished cell, so every term below is zero by construction: an interaction needs all four corners of its 2 x 2 sub-table before it can say anything. The cell counts beside each mean are the honest content here.

**retrieval x contextualization — hit@10** (grand mean 0.8750)

| retrieval_mode \ context_mode | plain (n) | contextual_prefix (n) | late_chunking (n) |
|---|---|---|---|
| dense | 0.8500 (1), i=0.0000 | missing | missing |
| hybrid | 0.9000 (1), i=0.0000 | missing | missing |
| rerank | missing | missing | missing |

Corners behind the grid above: (dense, plain) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06; (hybrid, plain) -> grid-fixed-hybrid-plain-20261030T125429-6170ae66.

**chunk strategy x retrieval — hit@10** (grand mean 0.8750)

| chunk_strategy \ retrieval_mode | dense (n) | hybrid (n) | rerank (n) |
|---|---|---|---|
| fixed | 0.8500 (1), i=0.0000 | 0.9000 (1), i=0.0000 | missing |
| recursive_parent_child | missing | missing | missing |

Corners behind the grid above: (fixed, dense) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06; (fixed, hybrid) -> grid-fixed-hybrid-plain-20261030T125429-6170ae66.

**chunk strategy x contextualization — hit@10** (grand mean 0.8750)

| chunk_strategy \ context_mode | plain (n) | contextual_prefix (n) | late_chunking (n) |
|---|---|---|---|
| fixed | 0.8750 (2), i=0.0000 | missing | missing |
| recursive_parent_child | missing | missing | missing |

Corners behind the grid above: (fixed, plain) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66.


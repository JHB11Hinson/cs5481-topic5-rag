# The 18-cell matrix

Every row is one declared cell. `missing` means the cell produced no run that could be read: it is printed, never dropped, so the table always has the design's row count.

- runs root: `D:\DE Project\wt\exp\runs`
- cells: 18 declared, 12 finished, 1 unfinished, 0 unreadable, 5 absent
- joined by recomputed config digest, never by timestamp; 0 cell(s) carry a stale digest in `grid.json` (see `matrix.json`)
- `abst. t` is the cell's own `generate.abstain_score_threshold`; it differs per retrieval level because each level is scored on its own scale
- `abstention working point` is the threshold the calibrated sweep chose for that cell's score scale, joined through `reports/abstention/working-points.json` on the `applies_to_run_ids` list; `missing` means no sweep covered this cell's run

| # | cell | chunk | retrieval | context | run id | items | abst. t | abstention working point | hit@10 | MRR | nDCG@10 | cit. prec. | cit. rec. | span hit | over-abst. | abst. rec. | p50 ms | p95 ms | CNY/1k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | cell-fixed-dense-plain | fixed | dense | plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | 60 | 0.2000 | t=0.5706 raw=0.5706 | 0.8500 | 0.4817 | 0.5697 | 1.0000 | 0.8750 | 1.0000 | 0.1000 | 1.0000 | 17.3 | 21.3 | 9.2745 |
| 2 | cell-fixed-dense-contextual_prefix | fixed | dense | contextual_prefix | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | 60 | 0.2000 | t=0.5706 raw=0.5706 | 0.8250 | 0.4180 | 0.5145 | 0.9818 | 0.8000 | 0.9818 | 0.1500 | 1.0000 | 9008.5 | 32566.8 | 9.3053 |
| 3 | cell-fixed-dense-late_chunking | fixed | dense | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 4 | cell-fixed-hybrid-plain | fixed | hybrid | plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | 60 | 0.0100 | t=0.2824 raw=0.028606 | 0.9000 | 0.6529 | 0.7163 | 0.9846 | 0.9500 | 0.9846 | 0.0500 | 1.0000 | 39.9 | 7502.5 | 8.4638 |
| 5 | cell-fixed-hybrid-contextual_prefix | fixed | hybrid | contextual_prefix | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | 60 | 0.0100 | t=0.2824 raw=0.028606 | 0.8750 | 0.5737 | 0.6503 | 0.9844 | 0.9000 | 0.9844 | 0.0500 | 1.0000 | 11249.6 | 48847.1 | 8.9954 |
| 6 | cell-fixed-hybrid-late_chunking | fixed | hybrid | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 7 | cell-fixed-rerank-plain | fixed | rerank | plain | grid-fixed-rerank-plain-20261030T125648-57be667d | 60 | 0.0000 | t=0.2000 raw=0.426134 | 0.9000 | 0.6044 | 0.6743 | 0.9206 | 0.8750 | 0.9206 | 0.0250 | 1.0000 | 8718.1 | 16211.6 | 8.7896 |
| 8 | cell-fixed-rerank-contextual_prefix | fixed | rerank | contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | 60 | 0.0000 | t=0.2000 raw=0.426134 | 0.8750 | 0.6184 | 0.6786 | 0.9500 | 0.9500 | 0.9500 | 0.0250 | 1.0000 | 5162.7 | 11212.8 | 8.4302 |
| 9 | cell-fixed-rerank-late_chunking | fixed | rerank | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 10 | cell-recursive_parent_child-dense-plain | recursive_parent_child | dense | plain | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | 60 | 0.2000 | t=0.5706 raw=0.5706 | 0.8500 | 0.4792 | 0.5681 | 0.9577 | 0.9000 | 0.9577 | 0.0500 | 1.0000 | 6764.7 | 27929.1 | 9.3342 |
| 11 | cell-recursive_parent_child-dense-contextual_prefix | recursive_parent_child | dense | contextual_prefix | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | 60 | 0.2000 | missing | 0.8750 | 0.5045 | 0.5920 | 1.0000 | 0.9750 | 1.0000 | 0.0250 | 1.0000 | 4139.1 | 15959.8 | 9.1211 |
| 12 | cell-recursive_parent_child-dense-late_chunking | recursive_parent_child | dense | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 13 | cell-recursive_parent_child-hybrid-plain | recursive_parent_child | hybrid | plain | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | 60 | 0.0100 | t=0.2824 raw=0.028606 | 0.9000 | 0.6521 | 0.7152 | 0.9571 | 1.0000 | 0.9571 | 0.0000 | 1.0000 | 37.0 | 8020.2 | 8.5350 |
| 14 | cell-recursive_parent_child-hybrid-contextual_prefix | recursive_parent_child | hybrid | contextual_prefix | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | 60 | 0.0100 | missing | 0.9000 | 0.6432 | 0.7084 | 0.9753 | 0.9750 | 0.9753 | 0.0250 | 1.0000 | 4406.8 | 16544.1 | 8.4614 |
| 15 | cell-recursive_parent_child-hybrid-late_chunking | recursive_parent_child | hybrid | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| 16 | cell-recursive_parent_child-rerank-plain | recursive_parent_child | rerank | plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | 60 | 0.0000 | t=0.2000 raw=0.426134 | 0.9000 | 0.5985 | 0.6707 | 1.0000 | 0.9000 | 1.0000 | 0.0250 | 1.0000 | 8043.0 | 34498.6 | 9.5427 |
| 17 | cell-recursive_parent_child-rerank-contextual_prefix | recursive_parent_child | rerank | contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | 60 | 0.0000 | missing | 0.9000 | 0.5880 | 0.6621 | 0.9516 | 0.8500 | 0.9516 | 0.0500 | 1.0000 | 8712.5 | 38419.4 | 8.9514 |
| 18 | cell-recursive_parent_child-rerank-late_chunking | recursive_parent_child | rerank | late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |

## Main effects

Each mean is over the cells that finished with a non-missing value; the cell count travels beside it, because a level resting on one cell is not the same claim as a level resting on six.

**chunk strategy — hit@10** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| fixed | 0.8708 | 6 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-fixed-rerank-plain-20261030T125648-57be667d, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 |
| recursive_parent_child | 0.8875 | 6 | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |

**chunk strategy — citation precision** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| fixed | 0.9702 | 6 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-fixed-rerank-plain-20261030T125648-57be667d, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 |
| recursive_parent_child | 0.9736 | 6 | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |

**retrieval — hit@10** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| dense | 0.8500 | 4 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 |
| hybrid | 0.8938 | 4 | grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 |
| rerank | 0.8938 | 4 | grid-fixed-rerank-plain-20261030T125648-57be667d, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |

**retrieval — citation precision** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| dense | 0.9849 | 4 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 |
| hybrid | 0.9754 | 4 | grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 |
| rerank | 0.9556 | 4 | grid-fixed-rerank-plain-20261030T125648-57be667d, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |

**contextualization — hit@10** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| plain | 0.8833 | 6 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-rerank-plain-20261030T125648-57be667d, grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 |
| contextual_prefix | 0.8750 | 6 | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |
| late_chunking | missing | 0 | missing |

**contextualization — citation precision** (over 12 cells)

| level | mean | cells | run ids |
|---|---|---|---|
| plain | 0.9700 | 6 | grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-rerank-plain-20261030T125648-57be667d, grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 |
| contextual_prefix | 0.9738 | 6 | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a |
| late_chunking | missing | 0 | missing |

## Interactions

The term is `mean(i,j) - mean(i) - mean(j) + grand mean`: zero when the two factors add up on this metric, and the sign says which corner beats the additive prediction.

**retrieval x contextualization — hit@10** (grand mean 0.8792)

| retrieval_mode \ context_mode | plain (n) | contextual_prefix (n) | late_chunking (n) |
|---|---|---|---|
| dense | 0.8500 (2), i=-0.0042 | 0.8500 (2), i=0.0042 | missing |
| hybrid | 0.9000 (2), i=0.0021 | 0.8875 (2), i=-0.0021 | missing |
| rerank | 0.9000 (2), i=0.0021 | 0.8875 (2), i=-0.0021 | missing |

Corners behind the grid above: (dense, plain) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e; (dense, contextual_prefix) -> grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3; (hybrid, plain) -> grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e; (hybrid, contextual_prefix) -> grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64; (rerank, plain) -> grid-fixed-rerank-plain-20261030T125648-57be667d, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910; (rerank, contextual_prefix) -> grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a.

**chunk strategy x retrieval — hit@10** (grand mean 0.8792)

| chunk_strategy \ retrieval_mode | dense (n) | hybrid (n) | rerank (n) |
|---|---|---|---|
| fixed | 0.8375 (2), i=-0.0042 | 0.8875 (2), i=0.0021 | 0.8875 (2), i=0.0021 |
| recursive_parent_child | 0.8625 (2), i=0.0042 | 0.9000 (2), i=-0.0021 | 0.9000 (2), i=-0.0021 |

Corners behind the grid above: (fixed, dense) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-dense-contextual_prefix-20261030T142519-d947855e; (fixed, hybrid) -> grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950; (fixed, rerank) -> grid-fixed-rerank-plain-20261030T125648-57be667d, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222; (recursive_parent_child, dense) -> grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3; (recursive_parent_child, hybrid) -> grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64; (recursive_parent_child, rerank) -> grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a.

**chunk strategy x contextualization — hit@10** (grand mean 0.8792)

| chunk_strategy \ context_mode | plain (n) | contextual_prefix (n) | late_chunking (n) |
|---|---|---|---|
| fixed | 0.8833 (3), i=0.0083 | 0.8583 (3), i=-0.0083 | missing |
| recursive_parent_child | 0.8833 (3), i=-0.0083 | 0.8917 (3), i=0.0083 | missing |

Corners behind the grid above: (fixed, plain) -> grid-fixed-dense-plain-20261030T124637-8ae4eb06, grid-fixed-hybrid-plain-20261030T125429-6170ae66, grid-fixed-rerank-plain-20261030T125648-57be667d; (fixed, contextual_prefix) -> grid-fixed-dense-contextual_prefix-20261030T142519-d947855e, grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950, grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222; (recursive_parent_child, plain) -> grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e, grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e, grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910; (recursive_parent_child, contextual_prefix) -> grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3, grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64, grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a.


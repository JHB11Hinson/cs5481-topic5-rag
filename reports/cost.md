# System cost

Tokens are the run's own counters, split by the component that spent them. Money is the run's recorded USD cost converted at the fixed rate in `run.py`; `CNY/1k` is that figure scaled to 1,000 questions.

| cell | run id | generator | generation in | generation out | CNY total | CNY/1k | index size | chunks | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| cell-fixed-dense-plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | deepseek-v4.1-flash | 415147 | 35261 | 0.5565 | 9.2745 | 22.9 MiB | 2318 | 17.3 | 21.3 |
| cell-fixed-dense-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-hybrid-plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | deepseek-v4.1-flash | 387766 | 29952 | 0.5078 | 8.4638 | 22.9 MiB | 2318 | 39.9 | 7502.5 |
| cell-fixed-hybrid-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-fixed-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-dense-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-hybrid-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-plain | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-contextual_prefix | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| cell-recursive_parent_child-rerank-late_chunking | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |

Embedding and reranking run locally, so their cost is electricity rather than a line item; the money in this table is tokens.


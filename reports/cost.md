# System cost

Tokens are the run's own counters, split by the component that spent them. Money is the run's recorded USD cost converted at the fixed rate in `run.py`; `CNY/1k` is that figure scaled to 1,000 questions.

| cell | run id | generator | generation in | generation out | prefix in | prefix out | CNY total | CNY/1k | index size | chunks | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cell-fixed-dense-plain | grid-fixed-dense-plain-20261030T124637-8ae4eb06 | deepseek-v4.1-flash | 415147 | 35261 | missing | missing | 0.5565 | 9.2745 | 22.9 MiB | 2318 | 17.3 | 21.3 |
| cell-fixed-dense-contextual_prefix | grid-fixed-dense-contextual_prefix-20261030T142519-d947855e | deepseek-v4.1-flash | 415466 | 35643 | 0 | 0 | 0.5583 | 9.3053 | 22.9 MiB | 2318 | 9008.5 | 32566.8 |
| cell-fixed-dense-late_chunking | grid-fixed-dense-late_chunking-20261030T161040-76813f02 | deepseek-v4.1-flash | 178824 | 25960 | missing | missing | 0.2828 | 4.7134 | 22.9 MiB | 2318 | 3510.1 | 20394.7 |
| cell-fixed-hybrid-plain | grid-fixed-hybrid-plain-20261030T125429-6170ae66 | deepseek-v4.1-flash | 387766 | 29952 | missing | missing | 0.5078 | 8.4638 | 22.9 MiB | 2318 | 39.9 | 7502.5 |
| cell-fixed-hybrid-contextual_prefix | grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950 | deepseek-v4.1-flash | 406824 | 33157 | 0 | 0 | 0.5397 | 8.9954 | 22.9 MiB | 2318 | 11249.6 | 48847.1 |
| cell-fixed-hybrid-late_chunking | grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39 | deepseek-v4.1-flash | 281267 | 31243 | missing | missing | 0.4064 | 6.7740 | 22.9 MiB | 2318 | 7988.7 | 17102.8 |
| cell-fixed-rerank-plain | grid-fixed-rerank-plain-20261030T125648-57be667d | deepseek-v4.1-flash | 401174 | 31485 | missing | missing | 0.5274 | 8.7896 | 22.9 MiB | 2318 | 8718.1 | 16211.6 |
| cell-fixed-rerank-contextual_prefix | grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222 | deepseek-v4.1-flash | 385995 | 29891 | 0 | 0 | 0.5058 | 8.4302 | 22.9 MiB | 2318 | 5162.7 | 11212.8 |
| cell-fixed-rerank-late_chunking | grid-fixed-rerank-late_chunking-20261030T163138-8f5d6ac0 | deepseek-v4.1-flash | 325632 | 34588 | missing | missing | 0.4642 | 7.7369 | 22.9 MiB | 2318 | 8515.1 | 28671.2 |
| cell-recursive_parent_child-dense-plain | grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e | deepseek-v4.1-flash | 410092 | 37420 | missing | missing | 0.5601 | 9.3342 | 21.7 MiB | 2203 | 6764.7 | 27929.1 |
| cell-recursive_parent_child-dense-contextual_prefix | grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3 | deepseek-v4.1-flash | 413246 | 33436 | 0 | 0 | 0.5473 | 9.1211 | 21.7 MiB | 2203 | 4139.1 | 15959.8 |
| cell-recursive_parent_child-dense-late_chunking | grid-recursive_parent_child-dense-late_chunking-20261030T164237-9b6dc31d | deepseek-v4.1-flash | 174881 | 31324 | missing | missing | 0.3003 | 5.0055 | 21.7 MiB | 2203 | 6644.9 | 33998.3 |
| cell-recursive_parent_child-hybrid-plain | grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e | deepseek-v4.1-flash | 391270 | 30144 | missing | missing | 0.5121 | 8.5350 | 21.7 MiB | 2203 | 37.0 | 8020.2 |
| cell-recursive_parent_child-hybrid-contextual_prefix | grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64 | deepseek-v4.1-flash | 392468 | 28740 | 0 | 0 | 0.5077 | 8.4614 | 21.7 MiB | 2203 | 4406.8 | 16544.1 |
| cell-recursive_parent_child-hybrid-late_chunking | grid-recursive_parent_child-hybrid-late_chunking-20261030T165835-0cecad68 | deepseek-v4.1-flash | 278098 | 31085 | missing | missing | 0.4026 | 6.7107 | 21.7 MiB | 2203 | 7671.7 | 17729.6 |
| cell-recursive_parent_child-rerank-plain | grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910 | deepseek-v4.1-flash | 416980 | 38824 | missing | missing | 0.5726 | 9.5427 | 21.7 MiB | 2203 | 8043.0 | 34498.6 |
| cell-recursive_parent_child-rerank-contextual_prefix | grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a | deepseek-v4.1-flash | 400274 | 34136 | 0 | 0 | 0.5371 | 8.9514 | 21.7 MiB | 2203 | 8712.5 | 38419.4 |
| cell-recursive_parent_child-rerank-late_chunking | grid-recursive_parent_child-rerank-late_chunking-20261030T170813-ddf8886b | deepseek-v4.1-flash | 304728 | 33117 | missing | missing | 0.4374 | 7.2902 | 21.7 MiB | 2203 | 9517.9 | 35337.5 |

Embedding and reranking run locally, so their cost is electricity rather than a line item; the money in this table is tokens.


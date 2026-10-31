# Query pooling under late chunking: CLS vs mean

Probe over 40 answerable golden items, k = 10, using the **cached** late-chunked document vectors from `configs/grid/cell-recursive_parent_child-dense-late_chunking.yaml` (2203 chunks). Only the query pooling changes between the two columns.

| query pooling | hit@k | MRR |
|---|---|---|
| CLS (what the runs did, `ADR-0018`) | 0.2750 | 0.1514 |
| mean over query token states (what the spans do) | 0.0250 | 0.0250 |

Items the mean-pooled query recovers and the CLS one misses: **0**; the reverse: **10**.

## Why this matters for the report

The dense cells under late chunking score 0.2750 hit@10 against 0.8500 for plain chunks. If the mean-pooled query recovers most of that gap, the loss is a property of this implementation's pooling choice, not of late chunking as a technique: the document side pools spans, so the query side must pool the same way or the two live in different spaces. If it does not recover, the loss belongs to the mechanism on this corpus and the report should say so plainly.

## Reproduce

```bash
HF_HUB_OFFLINE=1 python scripts/late_pooling_probe.py
```

## Per-item ranks

| item | type | CLS rank | mean rank |
|---|---|---|---|
| A001 | fact_lookup | miss | miss |
| A002 | fact_lookup | 7 | miss |
| A003 | fact_lookup | miss | miss |
| A004 | fact_lookup | 9 | miss |
| A005 | fact_lookup | miss | miss |
| A006 | fact_lookup | 1 | miss |
| A007 | fact_lookup | 5 | miss |
| A008 | fact_lookup | miss | miss |
| A009 | fact_lookup | miss | miss |
| A010 | fact_lookup | miss | miss |
| A011 | param_value | 1 | miss |
| A012 | param_value | miss | miss |
| A013 | param_value | miss | miss |
| A014 | param_value | miss | miss |
| A015 | param_value | miss | miss |
| A016 | param_value | miss | miss |
| A017 | param_value | 1 | miss |
| A018 | param_value | 3 | miss |
| A019 | table_content | 1 | miss |
| A020 | table_content | 1 | 1 |
| A021 | table_content | miss | miss |
| A022 | table_content | miss | miss |
| A023 | table_content | 7 | miss |
| A024 | table_content | miss | miss |
| A025 | table_content | miss | miss |
| A026 | table_content | 8 | miss |
| A027 | multi_hop | miss | miss |
| A028 | multi_hop | miss | miss |
| A029 | multi_hop | miss | miss |
| A030 | multi_hop | miss | miss |
| A031 | multi_hop | miss | miss |
| A032 | multi_hop | miss | miss |
| A033 | multi_hop | miss | miss |
| A034 | multi_hop | miss | miss |
| A035 | concept | miss | miss |
| A036 | concept | miss | miss |
| A037 | concept | miss | miss |
| A038 | concept | miss | miss |
| A039 | concept | miss | miss |
| A040 | concept | miss | miss |

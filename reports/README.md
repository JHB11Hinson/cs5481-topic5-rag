# `reports/` is generated, not written

Every file in this directory is produced by one command. Editing anything here by hand creates a number that no run directory backs, which is the one thing this bundle exists to prevent. Change the code or the runs, then regenerate.

```
python -m ragqa aggregate --runs "D:\DE Project\wt\exp\runs" --out reports
```

That is the exact command used to produce this snapshot: 2 of 18 cells finished, 16 printed as `missing`.

## What each file answers

| file | answers |
|---|---|
| `matrix.md` | the 18-cell table, main effects per factor, and two-way interactions |
| `matrix.csv` | the same cells, one row per cell, for a spreadsheet or a plot |
| `matrix.json` | the cells plus every effect table and the join metadata, for code |
| `significance.md` | bootstrap intervals per cell and McNemar on the factor contrasts |
| `significance.csv` | the same intervals and contrasts, machine readable |
| `judges.md` | Cohen's kappa per verification layer and the NLI x judge confusion grid |
| `judges.csv` | the per-layer calibration numbers |
| `cost.md` | tokens by component, CNY per 1,000 questions, index size, latency |
| `cost.csv` | the same cost table, machine readable |
| `figures.md` | which figure was drawn from which CSV |
| `figures/*.png` | sensitivity and abstention curves, redrawn from the CSVs |

## Protocol this bundle assumes

- a cell is joined to its run by the config digest recomputed from the cell's YAML; the digest stored in `configs/grid/grid.json` is reported as drift, not used
- intervals: 10000 bootstrap resamples, seed 20261030, resample unit = item
- paired tests: McNemar's exact test, two-sided
- a directory with no `metrics.json` is not a run; the cell is printed as `missing`

## Files in this snapshot

- `matrix.md`
- `matrix.csv`
- `matrix.json`
- `significance.md`
- `significance.csv`
- `judges.md`
- `judges.csv`
- `cost.md`
- `cost.csv`
- `figures.md`
- `figures/sweep-k.png`
- `figures/sweep-chunk.png`
- `figures/sweep-hops.png`
- `figures/abstention-hybrid.png`
- `figures/abstention-llm.png`
- `figures/abstention-rerank.png`
- `README.md`


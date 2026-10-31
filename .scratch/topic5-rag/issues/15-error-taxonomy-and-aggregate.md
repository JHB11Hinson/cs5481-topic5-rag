# 15: Error taxonomy and the generated report bundle

**What to build:** forty hand-inspected failures assigned to a fixed taxonomy, and one aggregation command that turns the run directories into the report's tables and figures so no number in the document is typed by hand.

**Blocked by:** 13, 14.

**Status:** done — nine classes over 275 events, and one command for every table

- [x] `notes/error-taxonomy.md` fixes nine classes and assigns 40 failures with one-line justifications and counts per class per cell
- [x] `ragqa aggregate` emits the 18-row matrix table, three sensitivity figures, the abstention PR curve, the judge agreement table, and the system cost table
- [x] Every table row prints the run id it came from
- [x] `reports/` is generated only; a regeneration from `runs/` reproduces it
- [x] Paired significance (McNemar) and bootstrap confidence intervals appear on the headline metrics

## Resolution

`notes/error-taxonomy.md` fixes nine classes, assigns forty hand-inspected failures with a
one-line justification each, and counts **275 events per class per cell** across all
eighteen cells. Six classes fire; over-abstention, under-abstention and span-out-of-bounds
are empty, and that emptiness is a result. Three corrections the two-cell version could not
see: `hit@10` is any-of over the gold quotes, so 56 of 196 evidence-loss events were
counted as hits and all-quote recall is 0.73 rather than 0.81; `context-budget-drop` is not
empty (29 chunks lost between k=10 and `llm.context_chunks=8`, 21 items answered anyway);
and all 64 abstentions on answerable items are accounted for by evidence loss, so there is
**zero** generator over-abstention.

`python -m ragqa aggregate --runs runs --out reports` emits the matrix, the main effects,
the paired contrasts, the judge table, the cost table and the figures, with every row
naming its run id and `reports/README.md` stating that the directory is generated. A
second run is byte-identical, PNGs included.

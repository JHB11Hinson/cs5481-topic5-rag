# 15: Error taxonomy and the generated report bundle

**What to build:** forty hand-inspected failures assigned to a fixed taxonomy, and one aggregation command that turns the run directories into the report's tables and figures so no number in the document is typed by hand.

**Blocked by:** 13, 14.

**Status:** ready-for-agent

- [ ] `notes/error-taxonomy.md` fixes nine classes and assigns 40 failures with one-line justifications and counts per class per cell
- [ ] `ragqa aggregate` emits the 18-row matrix table, three sensitivity figures, the abstention PR curve, the judge agreement table, and the system cost table
- [ ] Every table row prints the run id it came from
- [ ] `reports/` is generated only; a regeneration from `runs/` reproduces it
- [ ] Paired significance (McNemar) and bootstrap confidence intervals appear on the headline metrics

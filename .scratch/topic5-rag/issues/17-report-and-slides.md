# 17: Six-page report and the slides

**What to build:** the graded deliverables — a six-page report with introduction, methodology, experiments and discussion, references and appendix unlimited, slides appended at the end, and the contribution page as the last page of the main report.

**Blocked by:** 15, 16.

**Status:** done — six pages, sixteen slides appended, contribution page last

- [x] Methodology states the 18-cell design, the paired tests, the 60-item set, and the deliberate omissions with their reasons
- [x] Experiments present the matrix, the three curves, the abstention curve, judge agreement, error distribution, baselines, and system cost
- [x] Discussion argues from the error taxonomy rather than from the metric table, and states what would be done with more time
- [x] Every number traces to a run id
- [x] Slides appended; 15-minute structure with the demo at minute nine
- [x] Contribution page is the last page of the main report, before the slides

## Resolution

`reports/report.docx` runs to six pages of main content (`References` opens page 7), then
references, appendix, and the contribution page as page 10 — the last page before the
appended slides. `reports/submission.pdf` is 26 pages: 10 of report plus 16 of slides
(page counts re-checked independently of the build script). The deck is a fifteen-minute
structure with the demo at minute nine, and everything added late sits after it.

Methodology states the 18-cell design, the paired tests, the 60-item set with its strata,
and the deliberate omissions with their ADRs. Experiments carry the matrix with hit@10
bootstrap intervals, the three sensitivity curves, the abstention curve and its working
points, judge agreement, the 275-event error distribution, the four baselines and the cost
table, each naming its run id. Discussion argues from the taxonomy — 71% of classified
failures are evidence that never reached the prompt — and from the two null results and the
smaller-embedder collapse, and leads "with more time" with a mean-pooling encoder.

# Sixty-item golden set, paired evaluation

The golden QA set is 60 items — 40 answerable, 20 deliberately unanswerable — and every configuration is evaluated on the identical set. Comparisons between configurations are paired by question, tested with McNemar's test on hit/no-hit and bootstrap confidence intervals over questions.

Thirty items was the original plan and it was too small for the design it has to feed. Two separate problems, both arithmetic. First, an abstention precision-recall curve needs enough negatives to give the recall axis resolution: with 6 negatives the curve has 7 usable points and degenerates into a staircase; 20 negatives gives 21 points, which is the minimum for a curve a reader can interpret. Second, the 18-cell matrix is compared pairwise, and the paired test's power depends on discordant pairs, not on sample size in the abstract. At a 0.75-versus-0.90 difference with roughly 20% discordance, 24 answerable items yield about 5 discordant pairs (4:1, McNemar two-sided p≈0.38 — undetectable); 60 answerable items yield about 12 (10:2, p≈0.04 — detectable). The golden set size, not the number of cells, is what decides whether any claim in the report can carry a significance marker.

Answerable items are stratified so that a single question type cannot dominate the mean: fact lookup 10, parameter/function values 8, table or code-block content 8, multi-hop across two documents 8, conceptual explanation 6. Unanswerable items are near-misses — questions that are topically adjacent to something the documentation does cover, phrased so that a system with a broken abstention path will answer them confidently. Obvious questions ("what is the capital of France") test nothing.

Evidence is anchored as `(doc_id, quoted evidence sentence)` rather than a chunk id: chunk ids change with every chunk strategy, and the golden set must outlive them. Re-chunking cannot break the set.

## Consequences

Labeling 60 items is the largest single human task in the project and it sits on the critical path — a draft of 20 must exist before the first end-to-end run, so the set is built in two passes (v0 at 20 items, v1 at 60). LLM-drafted candidate questions are allowed and must be recorded as such, with the human edit noted per item; the provenance field exists precisely so this stays honest instead of becoming an unmentioned shortcut.

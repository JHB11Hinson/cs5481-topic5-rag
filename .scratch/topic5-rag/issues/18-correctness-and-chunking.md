# 18: Answer correctness and the chunking comparison

**What to build:** the two measurements `AGENTS.md` mandates and an earlier draft did not report — answer correctness against the Golden QA Set's reference answers, and the impact of the two chunking strategies on retrieval quality.

**Blocked by:** 08 (the golden set) and 12 (the cells to measure).

**Status:** done

The course brief requires "at least two chunking strategies … report their impact on retrieval quality" and "at least 20 question–answer pairs … report retrieval hit rate **and answer correctness**". The project had citation support, faithfulness and abstention, and no answer-correctness number anywhere; `GLOSSARY.md` avoids the word, which is a vocabulary choice, not an exemption.

- [x] `ragqa/correctness.py` + `scripts/score_correctness.py` judge every answerable item against its `reference_answer` with `deepseek-v4-pro`, cached by content hash
- [x] Three numbers kept distinct: accuracy over all 40 answerable items (an abstention counts as not correct), accuracy over the items the system chose to answer, and the abstention count
- [x] `reports/correctness.{json,csv}` and `notes/correctness.md`: per-cell rows with bootstrap 95% CIs resampled over items, judge calls, and cost
- [x] `scripts/chunk_comparison.py` pairs every `fixed` cell with its `recursive_parent_child` twin and reports retrieval, citation, abstention, latency and ¥ deltas with paired McNemar
- [x] The mechanism is reported, not just the outcome: child counts, mean and p95 tokens, share ending mid-sentence, share carrying a table row or code fence, share over budget
- [x] `reports/chunking.{json,csv}` and `notes/chunking-comparison.md`, with an absent twin reported as `pending` rather than zero
- [x] 19 tests, no network or GPU needed for them

## Resolution

Correctness, eighteen cells: **0.4250–0.9000** over all 40 answerable items and
**0.7083–0.9474** over the items the system chose to answer, 0–6 abstentions per cell, at
¥0.3104 for 656 judge calls on the first pass (the rerun is free: every claim is cached).
The spread is informative — the two dense late-chunking cells are the low end at 0.4250,
which is the retrieval collapse showing up as wrong answers rather than as missing
citations.

Chunking, nine pairs: `recursive_parent_child` minus `fixed` moves hit@10 by +0.05,
+0.025 or 0 in every pair, with **no pair below p = 0.5**; the only paired result under
0.05 in the whole table is dense/contextual_prefix citation support, +7 items at
p = 0.0156 — against rerank/contextual_prefix at −4 items and p = 0.22, so the direction
is not consistent. The mechanism numbers explain why the strategies behave alike here:
recursive yields 2,203 children with mean 312 words and p95 543, keeps 477 chunks over the
512-word budget of which 86.8% carry a table row or code fence, and cuts mid-sentence
endings from 57.4% to 18.7% — but **the atomic-table hypothesis is not testable on this
set**, because all eight `table_content` items are hit 8/8 by both strategies, leaving the
paired test without a single discordant pair. That is written up as "not testable", not as
"confirmed".

`python -m ragqa.selftest` green (19 tests added); both scripts are read-only over a run
root and spend nothing on a rerun.

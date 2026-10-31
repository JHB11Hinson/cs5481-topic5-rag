"""Replace §3.9 and §4 of reports/report.md with the final-pass prose.

    python .scratch/topic5-rag/splice_tail.py
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

THREATS = """### 3.9 Threats to validity

- **Citation numbers are containment, not support** (§3.4), and **abstention in the matrix is the generator's, not the threshold's** (§3.2).
- **hit@10 is any-of, not recall.** `evaluate._first_hit_rank` returns on the first gold quote it locates, so a multi-hop item with one leg retrieved counts as a hit: 56 of the 196 evidence-loss events sit on items the matrix scored as hits, and recall over *every* gold quote is **0.73**, not the 0.81 the matrix averages.
- **Rank metrics have no interval**: hit@10 is bootstrapped over items, while MRR and nDCG@10 print `missing`, because a committed run directory records which items were missed, not where the evidence ranked (§3.1).
- **The taxonomy counts lost evidence, not wrong answers.** Every cell ran with `judge_enabled = false`, so it is an upper bound on answer errors, and its forty rows are a stratified sample sized for coverage, not for rates (§3.5).
- **Containment proves the quote is real, not that it is sufficient.** Fourteen golden items were read against the corpus at the group's authorisation (`notes/golden-audit.md`): one defect (`A038` asserts a rotation consequence its quote does not contain), three quotes containable but not self-locating, one item answerable from general knowledge, thirteen passes. `verified_by` stays `automated:corpus-anchored`, and this audit was performed by the implementing agent — not an independent human review.
- **The sweeps price parameters, not policies.** All three hop points share one trigger (0.426134), and the sweep cells run the 40 answerable items with no near-misses, so nothing there speaks to abstention.
- **Latency is cache-dominated and cost is one run's recorded USD scaled up** (§3.7), not a billing statement.
"""

DISCUSSION = """## 4 Discussion

The metric table says hybrid and reranked retrieval tie at 0.8792 hit@10, twenty-two points over dense. The taxonomy says something less flattering and more useful: **71 % of this system's failures are evidence that never reached the prompt** — 196 of 275 events — while the generator's own defects are 43 mangled or unparsable replies on a base of 1,080 item-cells. Nothing in that distribution is a scoring problem. `A028` misses `seal-best-practices` in all eighteen cells, `A034` and `A035` their own pages in all eighteen, `A030` in seventeen, under every ranker and both chunk strategies: the pages are absent, not mis-ranked.

That splitting matters because **the two families have different cures and only one of them is cheap.** Page absence — 157 events on 25 distinct items — is index recall against a corpus whose pages phrase mechanisms differently from the way the questions ask about them: a vocabulary and coverage problem, and no reranker touches it. Chunk-boundary loss — 39 events from 12 items, `A015` alone accounting for ten — is the class §3.6 shows chunking does not fix, because `fixed` and `recursive_parent_child` split tables the same way. The third family is not a failure to retrieve at all: 29 quote-bearing chunks were retrieved and then dropped between `retrieval.k = 10` and `llm.context_chunks = 8`, and 21 of those items answered correctly anyway. **Carrying two numbers that disagree costs recall for nothing**, and setting the window to k is a one-line change that should have been made before any of the sweeps.

**The generator is not the component refusing answers**, and the taxonomy proves it rather than asserting it: all 64 abstentions on answerable items are exactly the 64 items whose evidence was lost first — 43 document misses, 13 chunk misses, 8 window drops — and not one abstention had its complete evidence set inside the window. Zero generator over-abstention is therefore derived from the evidence accounting, which is a stronger claim than the count of refusals, and it means the abstention columns in §3.1 should be read as a retrieval report.

**The sensitivity curves say where the next point of recall is, and it is not a larger k.** Depth saturates at k = 20 while MRR peaks at k = 5, and citation precision peaks at k = 10 — the tail is recoverable and the head is not free, because the generator sees eight chunks however deep the retrieval went, which is the same window mismatch seen from the other side. The 512-word chunk, which the matrix uses, is the dominated point on its own curve: 256 words retrieves more (0.9500 against 0.9000) for ¥3.50 less per 1,000 questions and gives up citation precision to do it, so the honest reading is that chunk resolution was never tuned, only declared. The hop loop pays exactly once — the second round buys 2.5 recall points for ¥0.62, the third buys nothing — which is the answer the ticket asked for and also the cheapest experiment on the list.

The null results eliminate the two cheapest explanations of the dense–hybrid gap. If chunk boundaries were what mattered, the recursive strategy would have separated somewhere in nine pairs and did not. If index-side context were what mattered, the prefix would have separated in six strata and did not (citation p = 0.823803, abstention p = 0.581055). What did separate is the score scale: reranked retrieval loses 20 items to 8 on grounded citation (p = 0.035698) even though its hit@10 is identical to hybrid's — the cross-encoder, applied on top of an RRF ordering, throws away citations the fused ranking already had.

**Late chunking's collapse is the mechanism's, not our experiment's, and that is the finding we would defend.** It costs the dense branch 0.8500 → 0.2750 hit@10 and 54 of 240 paired retrieval items to plain (b = 0, p < 0.000001), while hybrid and rerank at 0.8750 show the level is survivable when a lexical branch or a cross-encoder can repair the ordering. The first explanation to rule out was our own pooling, since `ADR-0018` pools spans by mean and encodes queries by CLS; swapping the query side to mean pooling made it worse, 0.2750 → 0.0250 with ten items lost and none gained (`notes/late-pooling-probe.md`). So the incompatibility is not a choice we got wrong at the query: mean-pooling token states is off-distribution for a CLS-trained encoder, and the damage sits in the document vectors. Document-level context is therefore still untested on this corpus — what failed is `bge-m3` doing late chunking, not late chunking.

Two observations cut against our own headline numbers. The matrix's abstention columns look excellent — twenty near-misses refused in all eighteen cells — but that is the generator's judgement, not the calibrated threshold's work (§3.2), and the calibrated point that would refuse 17 of 20 near-misses on the dense scale was never in force. And the best correctness cells sit at 0.9000, which is 36 of 40: the residual four are the taxonomy's lost-evidence events and one fabricated span, the same failures seen from a different instrument.

**With more time**, in the order this argument justifies: set the context window equal to k and re-measure, since 29 dropped chunks and a dominated chunk size are both one-line changes; normalise markdown links before containment, which removes 8 of the 26 quote failures without touching the generator, and raise `max_tokens` for the three multi-hop items that exhaust it; re-run the late-chunking level on a mean-pooling encoder (`jina-embeddings-v2`, or an e5/gte model), the only experiment that tests the mechanism rather than our implementation of it; enable the judge on headline cells so citation precision stops meaning containment; adopt the four golden v2 quote extensions the audit proposes and re-run the matrix on them; and have a human read the remaining twenty-six items, the one threat no amount of compute removes.
"""


def main():
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("### 3.9 Threats to validity")
    end = text.index("## 5 References", start)
    text = text[:start] + THREATS + "\n" + DISCUSSION + "\n" + text[end:]
    REPORT.write_text(text, encoding="utf-8")
    print("replaced §3.9 and §4")


if __name__ == "__main__":
    main()

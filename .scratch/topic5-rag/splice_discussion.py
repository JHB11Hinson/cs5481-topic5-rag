"""Rewrite §4 to the final-pass argument, inside the six-page budget.

    python .scratch/topic5-rag/splice_discussion.py
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

DISCUSSION = """## 4 Discussion

The metric table says hybrid and reranked retrieval tie at 0.8792 hit@10, twenty-two points over dense. The taxonomy says something less flattering: **71 % of this system's failures are evidence that never reached the prompt** — 196 of 275 events — while the generator's own defects are 43 mangled or unparsable replies on a base of 1,080 item-cells. Nothing in that distribution is a scoring problem. `A028` misses `seal-best-practices` in all eighteen cells, `A034` and `A035` their own pages in all eighteen, `A030` in seventeen, under every ranker and both chunk strategies.

**The two families need different cures, and only one of them is cheap.** Page absence — 157 events on 25 distinct items — is index recall against a corpus that phrases mechanisms differently from the way the questions ask about them: a vocabulary problem no reranker touches. Chunk-boundary loss — 39 events from 12 items, `A015` alone ten of them — is the class §3.6 shows chunking does not fix, because both strategies split tables the same way. A third cost is not a failure at all: 29 quote-bearing chunks were retrieved and then dropped between `retrieval.k = 10` and `llm.context_chunks = 8`, and 21 of those items answered correctly anyway. Carrying two numbers that disagree costs recall for nothing, and setting the window to k is a one-line change that should have preceded every sweep.

**The generator is not the component refusing answers.** All 64 abstentions on answerable items are exactly the 64 items whose evidence was lost first — 43 document misses, 13 chunk misses, 8 window drops — and not one had its complete evidence set inside the window. Zero over-abstention is derived from that accounting rather than assumed, which is why §3.1's abstention columns should be read as a retrieval report.

**The curves say where the next point of recall is, and it is not a larger k.** Depth saturates at k = 20 while MRR peaks at k = 5 and citation precision at k = 10: the tail is recoverable and the head is not free, because the generator sees eight chunks however deep the retrieval went. The 512-word chunk the matrix uses is the dominated point on its own curve — 256 words retrieves more (0.9500 against 0.9000) for ¥3.50 less per 1,000 questions — so chunk resolution was declared rather than tuned. The hop loop pays exactly once: 2.5 recall points for ¥0.62, then nothing. The two nulls then eliminate the cheapest explanations of the dense–hybrid gap — chunk boundaries would have separated in nine pairs and did not, the prefix in six strata and did not (citation p = 0.823803) — and what did separate is the score scale, where the cross-encoder throws away 20 citations to 8 on top of an RRF ordering (§3.1).

**Late chunking's collapse belongs to the mechanism, not to our experiment.** It costs the dense branch 0.8500 → 0.2750 hit@10 and 54 of 240 paired retrieval items to plain (b = 0, p < 0.000001), while hybrid and rerank at 0.8750 show the level is survivable when a lexical branch repairs the ordering. The first suspect was our own pooling, since `ADR-0018` pools spans by mean and encodes queries by CLS; mean-pooling the query too made it worse — 0.0250 hit@10, ten items lost and none gained (`notes/late-pooling-probe.md`). So the incompatibility is not a query-side choice: mean-pooling token states is off-distribution for a CLS-trained encoder and the damage sits in the document vectors. What failed is `bge-m3` doing late chunking, not late chunking — which is why the mean-pooling encoder is the first experiment we would run.

**With more time**: set the context window to k, normalise markdown links before containment (8 of the 26 quote failures) and raise `max_tokens` for the three multi-hop items that exhaust it; re-run the late-chunking level on a mean-pooling encoder (`jina-embeddings-v2`, or an e5/gte model); enable the judge on headline cells so citation precision stops meaning containment; adopt the four golden v2 quote extensions the audit proposes and re-run the matrix on them; and have a human read the remaining twenty-six items, the one threat no amount of compute removes.
"""


def main():
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## 4 Discussion")
    end = text.index("## 5 References", start)
    REPORT.write_text(text[:start] + DISCUSSION + "\n" + text[end:], encoding="utf-8")
    print("replaced §4")


if __name__ == "__main__":
    main()

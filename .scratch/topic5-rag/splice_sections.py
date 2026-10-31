"""Replace whole sections of reports/report.md between two markdown headings.

    python .scratch/topic5-rag/splice_sections.py

The prose lives in this file so the replacement is one atomic edit per section
rather than a chain of fragile substring matches.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

SWEEPS = """### 3.3 The three sensitivity curves

Three one-parameter families run around one reference cell
(`configs/grid/cell-recursive_parent_child-rerank-plain.yaml`), each on the same 40
answerable items with the same corpus, embedder, generator and prices, so a difference
between two points is attributable to the swept key alone; `sweeps.check` refuses a cell
that differs outside its own parameter. All ten points finished
(`reports/sweeps/{k,chunk,hops}.{csv,md}`).

| curve | point | recall@k | MRR | cite P | ¥/1k |
|---|---|---|---|---|---|
| depth (`retrieval.k`) | 5 | 0.8750 | 0.6458 | 0.9655 | 6.8111 |
| | 10 | 0.9000 | 0.5985 | 1.0000 | 9.4650 |
| | 20 | 1.0000 | 0.6235 | 0.9206 | 10.7092 |
| | 40 | 1.0000 | 0.6148 | 0.9697 | 10.0959 |
| chunk (`chunk.size`) | 256 | 0.9500 | 0.7556 | 0.9538 | 5.9004 |
| | 512 | 0.9000 | 0.5985 | 1.0000 | 9.3990 |
| | 1024 | 0.9750 | 0.5664 | 0.9714 | 13.7861 |
| hops (`retrieval.hops`) | 1 | 0.9000 | 0.5985 | 1.0000 | 9.3990 |
| | 2 | 0.9250 | 0.6185 | 1.0000 | 10.0165 |
| | 3 | 0.9250 | 0.6185 | 1.0000 | 10.0348 |

![](assets/report/fig2-sweeps.png)

*Figure 2 — recall@k per swept point, with each point's CNY per 1,000 questions under its label. Source: `reports/sweeps/{k,chunk,hops}.csv`.*

**Depth buys recall and dilutes the ranking.** Recall@k runs 0.8750 → 0.9000 → **1.0000** at k = 20 and stays there at k = 40: four of the forty answerable items are reachable only beyond k = 10, and past k = 20 there is nothing left to find. Ranking quality moves the other way — MRR peaks at the shallowest depth (0.6458 at k = 5 against 0.5985 at k = 10, 0.6235 at k = 20 and 0.6148 at k = 40) and citation precision falls from 1.0000 to 0.9206 between k = 10 and k = 20. A deeper list recovers the tail and dilutes the head, because the generator sees eight chunks however many were retrieved: k = 20 buys recall that the window then discards (§3.5 counts the 29 chunks dropped between k = 10 and a window of 8).

**Mid-size chunks are dominated.** 256 words gives recall 0.9500 at ¥5.90; the 512-word point the matrix uses gives 0.9000 at ¥9.40 with citation precision 1.0000; 1,024 gives **0.9750** at **¥13.79**. The pre-registered expectation — precision peaking before recall — holds, and the 1,024 point buys 7.5 recall points over 512 for 47 % more money, the worst exchange on the page. The honest summary is that 512 pays the most and retrieves the least of the three, and only its perfect citation precision defends it.

**The hop loop pays once.** One round gives 0.9000 recall at ¥9.3990, two rounds **0.9250** at ¥10.0165, three rounds 0.9250 at ¥10.0348: the second buys 2.5 points for ¥0.62 per 1,000 questions, the third buys **nothing** and costs more, which is the pre-registered break-even — **hop 2** (`reports/sweeps/hops.md`). The loop rewrote 3 of 40 items and recovered one; the rest stopped on the first round or at the cap, and each run's stop-reason histogram is in its `hop_stats.json`. All three points share one trigger (0.426134, the v1 rerank working point), so this curve prices the loop, not the trigger.
"""

TAXONOMY = """### 3.5 The error distribution

All eighteen cells are classified: **275 events** over nine fixed classes, 40 of them hand-inspected with a written justification (`notes/error-taxonomy.md`, `.json`). An event is one `(item, layer)` pair and is assigned to the earliest layer that lost the answer.

| Class | Events | Share | What it is |
|---|---|---|---|
| `retrieval-document-miss` | 157 | 57 % | no chunk of an evidence page reached the returned depth |
| `retrieval-chunk-miss` | 39 | 14 % | the page arrived, the passage was split elsewhere |
| `context-budget-drop` | 29 | 11 % | the quote-bearing chunk ranked beyond the eight-chunk window |
| `citation-quote-not-in-chunk` | 26 | 9 % | the quoted span is not in the cited chunk |
| `generation-parse-failure` | 17 | 6 % | the reply could not be parsed into claims |
| `citation-chunk-not-retrieved` | 7 | 3 % | the claim cites a chunk that was never retrieved |
| over-abstention, under-abstention, span-out-of-bounds | 0 | — | see below: one is derived, two are structurally unreachable |
| **total** | **275** | | over 1,080 answerable item-cells |

**It fails before generation.** 196 of the 275 events (71 %) are evidence that never reached the prompt, and the generator's own defects are the small end: 26 mangled quotes and 17 unparsable replies. **Zero over-abstention is derived, not assumed**: all 64 abstentions on answerable items are exactly the 64 items whose evidence was lost first — 43 document misses, 13 chunk misses and 8 window drops — so not one abstention had its whole evidence set inside the window. That is a stronger statement than "the generator refused 64 times": the reader is not the component withholding answers. `generator-under-abstention` cannot fire because abstention recall on the twenty near-misses is 1.0000 in every cell, and `citation-span-out-of-bounds` is unreachable while spans are derived by string search rather than returned.

**The window costs more than it should.** With `retrieval.k = 10` and `llm.context_chunks = 8`, 29 quote-bearing chunks were retrieved and dropped before the prompt, and 21 of those items answered correctly anyway — which is why per-cell over-abstention (0.0250–0.4000) reads like a generator property when it is largely a window property. A015 in the dense cell, the two-cell note's over-abstention example, is really rank 9 of 8; it is one event, and it is also the item §3.9 flags for a bare table-row quote.

**Two families, and they need different fixes.** Page-level absence (157 events over 25 distinct items) is index recall: `A028` misses `seal-best-practices` in all eighteen cells, `A034` and `A035` their own pages in all eighteen, `A030` in seventeen, and no ranker moves them. Chunk-boundary loss (39 events from 12 items, `A015` alone ten of them) is the class §3.6 shows chunking does not fix. The 26 quote failures decompose four ways: 8 where the quote is faithful but the model flattened a markdown link (`[TLS](…)` written as `TLS`) and exact-string containment rejected it, 6 that splice text the chunk lacks, 9 whose text is in no chunk at all, and 3 that are verbatim in a different retrieved chunk. The 17 parse failures are three questions (`A031`, `A027`, `A029`) at `tokens_out = 3200` against `max_tokens = 1600`: the two-passage joins run out of output budget, and eleven of the 17 sit on items that had already lost evidence.

**What it cannot see.** Every cell ran with `judge_enabled = false`, so an answer that is wrong while its citations check out is invisible here: these are lost-evidence and malformed-output events — an upper bound on answer errors, not a wrong-answer count — and six of the forty sampled rows carry substantively correct answers.
"""


def splice(text, heading, replacement, next_heading):
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[:start] + replacement + "\n" + text[end:]


def main():
    text = REPORT.read_text(encoding="utf-8")
    text = splice(text, "### 3.3 The three sensitivity curves", SWEEPS,
                  "### 3.4 Judge agreement")
    text = splice(text, "### 3.5 The error distribution", TAXONOMY,
                  "### 3.6 Chunking strategy")
    REPORT.write_text(text, encoding="utf-8")
    print("spliced §3.3 and §3.5")
    for heading in re.findall(r"^### .*$", text, flags=re.M):
        print("  ", heading)


if __name__ == "__main__":
    main()

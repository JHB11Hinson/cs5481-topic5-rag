"""Second compression of the final pass: §3.3 without its table, §3.5 to three paragraphs.

    python .scratch/topic5-rag/splice_compact.py

Rationale, recorded because it is a content decision: the ten-row sweep table and the
three paragraphs beside it carried the same numbers twice, and the figure carries the
shape; the taxonomy's nine-row table is the only place its 275 events are broken down,
so it stays.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.md"

SWEEPS = """### 3.3 The three sensitivity curves

Three one-parameter families run around one reference cell (`configs/grid/cell-recursive_parent_child-rerank-plain.yaml`), each on the same 40 answerable items with the same corpus, embedder, generator and prices, so a difference between two points is attributable to the swept key alone; `sweeps.check` refuses a cell that differs outside its own parameter. All ten points finished (`reports/sweeps/{k,chunk,hops}.{csv,md}`), and Figure 2 draws them with each point's price.

![](assets/report/fig2-sweeps.png)

*Figure 2 — recall@k per swept point; the CNY per 1,000 questions for each point sits under its label. Source: `reports/sweeps/{k,chunk,hops}.csv`.*

**Depth buys recall and dilutes the ranking.** recall@k runs 0.8750 → 0.9000 → **1.0000** at k = 20 and stays there at k = 40 (¥6.81 / 9.47 / 10.71 / 10.10), so four of the forty answerable items are reachable only beyond k = 10 and past k = 20 there is nothing left to find. Ranking quality moves the other way: MRR peaks at the shallowest depth — 0.6458 at k = 5 against 0.5985 at k = 10, 0.6235 at k = 20, 0.6148 at k = 40 — and citation precision falls from 1.0000 to 0.9206 between k = 10 and k = 20. A deeper list recovers the tail and dilutes the head, because the generator sees eight chunks however many were retrieved: k = 20 buys recall the window then discards, which is the 29 dropped chunks §3.5 counts.

**Mid-size chunks are dominated.** 256 words gives recall 0.9500 for ¥5.90; the 512-word point the matrix uses gives 0.9000 for ¥9.40 with citation precision 1.0000; 1,024 gives **0.9750** for **¥13.79** (0.9714). The pre-registered expectation — precision peaking before recall — holds, and the 1,024 point buys 7.5 recall points over 512 for 47 % more money, the worst exchange on the page. The 512 point pays the most and retrieves the least of the three; only its perfect citation precision defends it.

**The hop loop pays once.** One round gives 0.9000 recall for ¥9.3990, two rounds **0.9250** for ¥10.0165, three rounds 0.9250 for ¥10.0348: the second buys 2.5 points for ¥0.62 per 1,000 questions and the third buys **nothing** while costing more, which is the pre-registered break-even — **hop 2** (`reports/sweeps/hops.md`). The loop rewrote 3 of 40 items and recovered one; the rest stopped on the first round or at the cap, with each run's stop-reason histogram in its `hop_stats.json`. All three points share one trigger (0.426134, the v1 rerank working point), so this curve prices the loop, not the trigger.
"""

TAXONOMY = """### 3.5 The error distribution

All eighteen cells are classified: **275 events** over nine fixed classes, 40 of them hand-inspected with a written justification each (`notes/error-taxonomy.{md,json}`). An event is one `(item, layer)` pair, assigned to the earliest layer that lost the answer.

| Class | Events | Share | What it is |
|---|---|---|---|
| `retrieval-document-miss` | 157 | 57 % | no chunk of an evidence page reached the returned depth |
| `retrieval-chunk-miss` | 39 | 14 % | the page arrived, the passage was split elsewhere |
| `context-budget-drop` | 29 | 11 % | the quote-bearing chunk ranked beyond the eight-chunk window |
| `citation-quote-not-in-chunk` | 26 | 9 % | the quoted span is not in the cited chunk |
| `generation-parse-failure` | 17 | 6 % | the reply could not be parsed into claims |
| `citation-chunk-not-retrieved` | 7 | 3 % | the claim cites a chunk that was never retrieved |
| over-abstention, under-abstention, span-out-of-bounds | 0 | — | one is derived, two are structurally unreachable (below) |
| **total** | **275** | | over 1,080 answerable item-cells |

**It fails before generation, and zero over-abstention is derived, not assumed.** 196 of the 275 events (71 %) are evidence that never reached the prompt; the generator's own defects are 43 mangled or unparsable replies on a base of 1,080 item-cells. All 64 abstentions on answerable items are exactly the 64 items whose evidence was lost first — 43 document misses, 13 chunk misses and 8 window drops — so not one abstention had its complete evidence set inside the window. That accounting is a stronger claim than the count of refusals: the reader is not the component withholding answers. `generator-under-abstention` cannot fire because abstention recall on the twenty near-misses is 1.0000 in every cell, and `citation-span-out-of-bounds` is unreachable while spans are derived by string search rather than returned.

**Two families, and the window is a third cost that is not an error at all.** Page absence (157 events on 25 distinct items) is index recall: `A028` misses `seal-best-practices` in all eighteen cells, `A034` and `A035` their own pages in all eighteen, `A030` in seventeen, and no ranker moves them. Chunk-boundary loss (39 events from 12 items, `A015` alone ten) is the class §3.6 shows chunking does not fix. Separately, with `retrieval.k = 10` and `llm.context_chunks = 8`, 29 quote-bearing chunks were retrieved and dropped before the prompt and 21 of those items answered correctly anyway — which is why per-cell over-abstention (0.0250–0.4000) reads like a generator property when it is largely a window property, and why `A015` in the dense cell, the two-cell note's over-abstention example, is really rank 9 of 8. Of the 26 quote failures, 8 are faithful quotes whose markdown link the model flattened (`[TLS](…)` written as `TLS`), so 8 of 26 disappear if containment normalises links before comparing; the 17 parse failures are three questions at `tokens_out = 3200` against `max_tokens = 1600`, eleven of them on items that had already lost evidence.
"""


def replace(text, heading, replacement, next_heading):
    start = text.index(heading)
    end = text.index(next_heading, start)
    return text[:start] + replacement + "\n" + text[end:]


def main():
    text = REPORT.read_text(encoding="utf-8")
    text = replace(text, "### 3.3 The three sensitivity curves", SWEEPS,
                   "### 3.4 Judge agreement")
    text = replace(text, "### 3.5 The error distribution", TAXONOMY,
                   "### 3.6 Chunking strategy")
    REPORT.write_text(text, encoding="utf-8")
    print("compacted §3.3 and §3.5")


if __name__ == "__main__":
    main()

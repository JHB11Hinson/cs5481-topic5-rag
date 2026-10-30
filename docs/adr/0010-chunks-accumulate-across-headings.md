# Recursive chunks accumulate across headings; headings do not bound them

The recursive strategy builds child chunks by accumulating units — sentence, table, or fenced code block — up to a word budget, and records the heading path of the unit that starts each chunk. It does not stop at a heading. Parents are consecutive groups of children within one document.

The first implementation did stop at headings, following the usual "split on heading, then paragraph, then sentence" recipe. Measured on this corpus it collapses: 9,444 sections across 1,268 documents with a median of 31 words and a p90 of 163. A heading-bounded splitter therefore produces children whose size is dictated by the documentation's heading density, not by the configured budget — mean 56 to 67 words whether the target was 128, 192, or 256 — and parents that are indistinguishable from children. Small-to-big stops being small-to-big, and the chunk-strategy factor stops being a real comparison, because the two levels differ only in the arbitrary point at which a word window is cut.

Accumulating across headings keeps the two things that actually matter and drops the one that does not. Sentence boundaries are respected, so chunks stop ending mid-sentence; tables and code blocks are atomic, so a table is never sliced between two chunks while a fixed window does exactly that; and the heading path travels with each chunk so a chunk still says where it came from. What is lost is the guarantee that one chunk equals one section — which the corpus's section sizes made unachievable anyway.

## Consequences

`share_containing_table_row` and `share_ending_mid_sentence` in `chunk_stats.json` become the two numbers that distinguish the strategies, and they should diverge sharply. The chunk-size sensitivity sweep (ticket 13) is now the only place where chunk size is isolated as a variable, since the two strategies no longer share a plausible common target. A table or code block larger than the budget is kept whole rather than split; its share is recorded so a reader can see how often the budget was exceeded.

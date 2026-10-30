# Contextualization is a three-level factor, not a switch

The third experimental factor has three levels — plain chunks, contextual prefixes, and late chunking — giving an 18-cell matrix of chunk strategy (2) × retrieval mode (3) × contextualization (3).

The survey of thirteen mature RAG systems found that neither mechanism ships in any open-source implementation: contextual retrieval, where a generated sentence situating the chunk in its document is prepended before indexing, appears only in Anthropic's write-up; late chunking, where the whole document is encoded first and chunk vectors are pooled from its token embeddings, appears only in Jina's paper. Those are the two places where this project can do something a reader cannot point at an existing product for. Putting them in the same factor makes the comparison the story rather than an appendix: what does giving a chunk document-level context actually buy, and does encoding order matter.

Late chunking is viable here only because bge-m3 accepts 8192 tokens — a 512-token encoder could not do it. That constraint is worth recording, since it is the reason a reader might otherwise assume the technique was overlooked.

## Consequences

A three-level factor costs 50% more generation calls than a switch (1,080 versus 720 for the matrix), and late chunking changes the embedding step from per-chunk batched encoding to per-document encoding plus span pooling, so it cannot share the chunk-level embedding cache the other two levels use. Two cache namespaces, not one. If late chunking turns out to be unimplementable within the schedule, it degrades to a two-point comparison reported separately, and the matrix stays at 12 cells.

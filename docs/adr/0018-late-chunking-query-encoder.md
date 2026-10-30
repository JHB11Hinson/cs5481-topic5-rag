# A late-chunked document and its query are encoded by different objects, on purpose

In `context.mode: late_chunking` a document is encoded whole and each chunk's vector is pooled from the token states covering its span (`ADR-0015`); the **query** is encoded by an ordinary chunk-level bge-m3 sentence encoder built beside it. The run records both under `context_stats.json` (`query_embedder`).

A query has no document span, so there is nothing to pool: asking the document encoder to embed it is a category error. The first implementation tried anyway — `run.py` called `embedder.embed([query])` on the document-level encoder — and every one of the six `late_chunking` matrix cells died with `AttributeError: no attribute 'embed'`. It survived six tickets of unit tests because the encoder had been probed on documents only and no cell had ever executed the query path. The fix took ten minutes; discovering it cost six cells and an hour of GPU.

Two consequences worth keeping.

**The comparability argument is the important one.** The contextualization factor asks how a *document* is represented in the index. If the query vector also changed between the three levels, the factor would be changing two things and no difference could be attributed to either. Pooling a query would do exactly that: a mean over the query's token states is a different embedding space from bge-m3's CLS-pooled sentence vector, so `late_chunking` would be measured against queries the other two levels never saw.

**A category error should fail in a sentence, not an attribute lookup.** `LateChunkingEmbedder.embed` now exists and raises `NotImplementedError` naming the correct object, and a test pins that behaviour. The class refuses to be something it is not, loudly.

## Consequences

Late chunking costs one extra model in memory — the pooled-vector encoder and the sentence encoder are both resident, 2.2 GB before the reranker — which is why the late cells are the ones that crowd a 6 GB card and why their window is 2,048 tokens rather than 8,192. `context_stats.json` carries `query_embedder` so a reader can see the two objects rather than infer them, and the report states that queries are CLS-pooled at every level while only documents are span-pooled at this one.

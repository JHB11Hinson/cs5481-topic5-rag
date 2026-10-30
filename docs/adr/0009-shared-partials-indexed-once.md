# Shared include fragments are indexed once, not inlined

A fragment included by exactly one page is inlined into that page. A fragment included by several pages is indexed once as its own document, and the referencing page keeps a `[shared partial: <doc_id>]` marker instead of a copy.

The measured tree has 623 distinct partials and 1,542 include references; 485 partials are shared, and the most-referenced ones appear in hundreds of API pages. Inlining everything turns one alert box into hundreds of near-identical chunks. Retrieval then finds the same boilerplate for unrelated questions, citation precision drops because the system can cite a copy that says nothing about the question, and the corpus grows by roughly a third of duplicated text — while the report's own survey lists near-duplicate documents as a failure mode mature systems engineer around explicitly. Copying the problem in at ingest time would poison every downstream number.

The cost of the chosen approach is that some answers need two hops: a page whose body is mostly a shared table now points at a fragment instead of containing it. That is a real retrieval difficulty and it is measurable, which is the point — it shows up in recall rather than silently inflating it.

## Consequences

`multi_hop` golden items can be built from the page-plus-fragment pairs that now exist naturally. Citations to fragment documents carry no public URL of their own, so the manifest records the first referring page as the citation target. If error analysis later shows that two-hop fragment answers dominate the misses, revisit and inline only the fragments whose text carries no page-specific meaning.

# The generator is handed the retrieved chunk, not its parent

`GLOSSARY.md` defines a parent chunk as the coarser chunk a retrieved chunk belongs to, and says the parent is what gets handed to the generator. This build hands the generator the retrieved child instead. The deviation is deliberate and is recorded here so the glossary stays a statement of intent rather than a claim about the code.

Citations are verified at chunk granularity (`ADR-0004`): a claim must quote text that occurs inside the chunk it names. If the generator read a 1,024-word parent while citing a 60-word child, every quote taken from the surrounding parent text would fail containment, and the failure rate would measure the parent/child bookkeeping rather than the model. The fix would be a second citation field carrying the parent span, which is a change to the citation contract, not a parameter.

The cost is real: a chunk near a boundary can be missing the sentence that makes it answerable, and the parent/grandparent expansion in the index would have helped there. The measured consequence is visible in the span hit rate and is reported, not papered over.

## Consequences

`retrieved[].parent_id` is carried through retrieval and into `predictions.jsonl`, so an experiment that switches the generator to parents can be run without re-indexing. The glossary entry for **Parent Chunk** keeps its meaning; the report states that the parent is available and unused, with this reason.

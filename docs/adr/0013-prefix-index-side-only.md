# The contextual prefix goes into the index, not into the prompt

A chunk's generated prefix is prepended before embedding and before the sparse term list, and it is never shown to the generator. The generation prompt carries the original chunk text.

The obvious alternative is to hand the model the contextualized text, which is what the contextual-retrieval write-up does. That alternative cannot coexist with `ADR-0004`. A claim is verified by locating its quoted text inside the chunk it cites, and if the model can quote the prefix, it can quote text that exists nowhere in the chunk, so a correct answer would be recorded as a containment failure. The measured quantity would then depend on which sentences the model preferred, which is not something a matrix can control.

Keeping the prompt plain also keeps the factor clean: the three contextualization levels then differ only in how the *index* represents a chunk, which is the claim being tested. Whether a prefix also helps the reader is a second question, and one this build does not answer.

## Consequences

The prefix has no effect on generation beyond better retrieval, so any gain is attributable to retrieval and nothing else. `chunks_contextual.jsonl` stores prefix, contextual text and original text side by side, so a later experiment that does put the prefix in the prompt can be run without touching the index code. The report states this boundary explicitly rather than letting a reader assume the model saw the prefix.

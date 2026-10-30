# 14: Baselines and swap controls

**What to build:** four comparison runs that make the system's contribution arguable — closed-book generation with no retrieval, whole-chapter long context instead of retrieval, a smaller embedding model, and a cheaper generator — each on the same 40 answerable items.

**Blocked by:** 12.

**Status:** ready-for-agent

- [ ] Closed-book baseline uses the same generator and prompt with the retrieval block empty
- [ ] Long-context baseline stuffs the full source chapter of the evidence document into the prompt and reports what the window costs and what it buys
- [ ] Embedding swap to all-MiniLM-L6-v2 reports retrieval and citation metrics under the same code path
- [ ] Generator swap to the cheaper model reports quality and cost shift
- [ ] Every baseline is a normal run directory with an id, not a notebook experiment
- [ ] The comparison table shows RAG versus no-RAG on correctness and on citation support, with paired significance

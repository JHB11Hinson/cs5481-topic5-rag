# 16: Demo UI where a citation is clickable

**What to build:** a single-screen chat demo that answers from the index, renders each claim with a citation marker, and opens the highlighted source span when the marker is clicked — plus an abstention case that visibly shows the best-scoring chunk and why it was judged insufficient.

**Blocked by:** 12.

**Status:** ready-for-agent

- [ ] Chainlit app serves one chosen run configuration without reloading models per question
- [ ] Citation markers open an element with document title, heading path, canonical URL, and highlighted span
- [ ] A near-miss question shows the abstention message alongside the best retrieved chunk
- [ ] Footer displays retrieval latency and the configuration name being served
- [ ] `notes/demo-script.md` records five questions with expected output as a fallback

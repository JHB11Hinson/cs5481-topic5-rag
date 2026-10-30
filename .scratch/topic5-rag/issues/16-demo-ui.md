# 16: Demo UI where a citation is clickable

**What to build:** a single-screen chat demo that answers from the index, renders each claim with a citation marker, and opens the highlighted source span when the marker is clicked — plus an abstention case that visibly shows the best-scoring chunk and why it was judged insufficient.

**Blocked by:** 12.

**Status:** done — Chainlit app, citation panel, abstention case

- [x] Chainlit app serves one chosen run configuration without reloading models per question
- [x] Citation markers open an element with document title, heading path, canonical URL, and highlighted span
- [x] A near-miss question shows the abstention message alongside the best retrieved chunk
- [x] Footer displays retrieval latency and the configuration name being served
- [x] `notes/demo-script.md` records five questions with expected output as a fallback

## Resolution

A citation marker is a `cl.Action`, not a link. Clicking it runs `open_citation`,
which rebuilds the panel from the process's own chunk store and sends a
`CitationCard` custom element carrying document title, heading path, canonical URL,
and the chunk text with the cited span wrapped in `<mark>`. The payload carries no
chunk text, so a panel cannot show stale evidence.

The five scripted questions are captured verbatim in `notes/demo-script.md`,
including A009 where the third claim is withheld as `quote_not_in_chunk`, and U008
where the system abstains and shows the best-scoring chunk (0.669) with the reason.

Chainlit 2.3.0 has no `cl.on_action` (it is `cl.action_callback`) and evaluates
element JSX in the browser, so the panel was validated by esbuild plus in-process
assertions on the element props rather than by eye. The app loads models once at
start and serves one configuration; the footer states latency and the configuration.

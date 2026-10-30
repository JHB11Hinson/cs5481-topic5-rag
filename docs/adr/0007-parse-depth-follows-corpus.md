# Parse depth follows the corpus, not the state of the art

There is no OCR, no table-structure recognition, and no PDF layout analysis. Parsing is a markdown/HTML structure-aware pass plus a stripped-plain-text pass, and the difference between them is one of the reported comparisons rather than a capability we build.

The corpus is a documentation repository written in markdown and rendered to HTML, so tables arrive as pipe-table text and code blocks as fenced text. Layout-analysis machinery — the DeepDoc / PaddleOCR / MinerU class of tools that the surveyed systems invest in — exists to recover structure that our source format never lost. Spending a week on it would produce no measurable gain on this corpus, and a reader who saw the effort would reasonably ask what it was for.

Keeping the stripped-text variant is the point: it makes the value of structure an observable quantity on our own corpus instead of an assumption inherited from systems that ingest PDFs. The discussion states the general claim — parse investment is bounded by what the source format still holds — and the two numbers that support it here.

## Consequences

If the corpus is ever swapped for a PDF-heavy one, this decision stops holding and the comparison becomes meaningless; the ADR is corpus-scoped on purpose. Extraction time also stays in the minutes, which keeps the harness fast enough for the smoke loop.

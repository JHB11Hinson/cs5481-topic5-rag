# Verify citations programmatically before judging them

The generator must emit structured claims, each carrying a document id, a chunk id, and a character span. A program checks that every span actually lies inside the retrieved context it cites, and only claims that survive that check are handed to support judges.

The brief asks for answers grounded in retrieved sources with citations. Letting the model write "[1]" in prose satisfies the letter of that and proves nothing: the check that matters is whether the cited span exists in the context the model was given, and whether that span contains the claim. The first question is a string operation, not a judgement call, so doing it in code removes a whole class of hallucinated citations before any model is asked to rule on the rest. It also defines the two failure modes the report can then separate: citations that point nowhere, and citations that point at real but irrelevant text.

Support is then judged twice — a local NLI cross-encoder for cheap coverage, and a stronger hosted model as the reference — with a hand-labelled sample of thirty cases measuring how far the two agree (Cohen's kappa). Metrics: citation precision (emitted citations that genuinely support their claim), citation recall (claims that carry any supporting citation), and span hit rate (citations whose span covers the evidence sentence).

## Consequences

Generation prompts must use structured output, which costs tokens and occasionally fails to parse; parse failures are recorded as their own error class rather than retried silently. Coverage of the judge is a budget decision: LLM-as-judge over every claim in every cell is the expensive line item, so it runs on all answerable questions of the headline cells and on a sample elsewhere.

# The retrieval-score threshold is a measurement, not a mechanism

`generate.abstain_score_threshold` is read by `StubGenerator` and **ignored by `LLMGenerator`**. Every shipped cell runs the hosted generator, so in the matrix the number does nothing: the model decides whether the documentation answers, and the threshold is inert. The v1 calibration still measured it properly — an 18-point sweep, a working point per score scale, a PR curve — and that is where its value ends. It is not wired into the answer path, and it should not be.

The reason is not laziness, it is what the curves say. Asked for a threshold that costs nothing, each scale answers with a point that buys nothing:

| scale | cheapest sensible cut | answerable items lost | near-misses refused |
|---|---|---|---|
| dense | 0.2000 (the floor of the grid) | 0 | **0** — nothing scores that low |
| hybrid | 0.2000 | **3 of 40** | 1 of 20 |
| rerank | 0.2000 | **6 of 40** | 8 of 20 |
| the shipped generator | — | 0 | **20 of 20** |

On dense there is no operating point at all: every one of the sixty items scores above the floor, and the first cut that refuses a near-miss is at 0.7353, where 38 of 40 answerable items fall below it. On hybrid and rerank the cheapest cut already costs answerable questions to refuse one near-miss to eight — and the generator refuses all twenty for free.

That pattern has a cause worth naming: **a near-miss is topically adjacent by construction.** It was written to use the corpus's vocabulary about a thing the corpus does not cover, so it embeds well and retrieves high. The score measures topical similarity, which is exactly the property a good near-miss maximises. A quantity that rises when the question is *harder* cannot gate the answer.

## Consequences

The knob stays, for three honest reasons: the stub path needs a threshold to demonstrate abstention offline, `ticket 11`'s artifact is the curve that this quantity produces, and removing a key from `ragqa/config.py`'s defaults would change every resolved-config digest and orphan fifty run directories. What changes is how it is described: a measurement of what the retriever could have decided, not a control the shipped system uses.

The mechanism that *is* wired is the one with the evidence behind it: the generator's own refusal, then containment, then the support judges (`ADR-0004`). All 64 abstentions on answerable items in the matrix are accounted for by lost evidence — 43 document misses, 13 chunk misses, 8 window drops — and that accounting is the reason to fix retrieval rather than to tune a threshold.

If someone does want the comparison on the record, it is one cell: gate at the cheapest cut, same items, and read the change off the curve — hybrid −0.075 recall, rerank −0.15, dense 0. The curves already predict it, which is why it is not run.

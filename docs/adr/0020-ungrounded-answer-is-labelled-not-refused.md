# A question the knowledge base cannot answer is labelled twice, not refused once

`generate.ungrounded_answer: abstain | assist` decides what happens after the grounded
call comes back empty. `abstain` is the measured default and every configuration under
`configs/grid/`, `configs/sweeps/` and `configs/baselines/` runs it. `assist` adds one
more call, shown to a person and to nothing else, whose answer is *labelled* as coming
from outside the documents.

The brief asks the system to "explicitly say so instead of guessing" when the knowledge
base does not contain the answer. Refusing outright satisfies that sentence and fails the
user: a documentation assistant that answers "not in the knowledge base" to a question
whose answer it knows perfectly well is not honest, it is unhelpful and dishonest at the
same time — the knowledge is present in the model and withheld from the reader. The
policy that satisfies both is the one the sentence does not forbid: say what is missing,
then answer anyway, with the answer marked.

## The three states, as the code emits them

| `answer_mode` | claims | `abstained` | what the reader sees |
|---|---|---|---|
| `grounded` | ≥ 1, each verified against its chunk | `false` | the answer, with a citation marker per claim |
| `abstained` | 0 | `true` | the gap sentence, the model's reason, the closest retrieved page |
| `ungrounded_general` | 0 | `true` | the fixed gap note, then the model's general paragraph, then the closest retrieved page |

`abstained` stays `true` in the third state on purpose. The knowledge base still did not
answer, so a metric that reads that flag — over-abstention, abstention recall, the
correctness denominator — must not silently start counting general prose as a retrieved
answer. What the flag cannot express is on the second axis: `answer_mode` is what the
screens and the taxonomy read.

## Two calls, two prompts

The grounded prompt keeps "Never use outside knowledge" absolute and is not edited by
this decision. When it returns nothing, and only then, a second call runs against
`UNGROUNDED_SYSTEM_PROMPT`, which says the documentation is absent, forbids invented
citations, chunk ids, titles, URLs and version numbers, and asks for at most six
sentences plus one line about what to verify. Splitting the prompts is the point: one
prompt that says both "answer only from context" and "answer from memory when context
fails" gives a model a choice it will make wrongly, and it would make a containment
failure indistinguishable from an instruction.

The gap note is not the model's. `generate.GAP_NOTE` is a fixed string prepended by the
code, so the label cannot be forgotten, softened or paraphrased, and a test asserts it is
the first thing in the answer rather than trusting a prompt to have been obeyed.

## What it costs, and where it is off

One extra call on the items that were already abstentions, capped at 400 output tokens by
`generate.ungrounded_max_tokens`. Nothing else changes: no run in `runs/` was produced
with the policy on, so not one number in the report depends on it. Turning it on is a
configuration edit in one file, `configs/real_llm.yaml`, where the demo is the only
surface that has a reader to be useful to.

A broken second call is not repaired into a fabricated one: if the model returns no
parseable answer, the plain abstention stands, and the tokens that were spent on the
failed call are still counted, because they were spent.

## Rejected alternatives

- **Always answer, never abstain.** Then the near-miss items — the twenty questions
  written to be topically adjacent and unanswered — would read as correct, the abstention
  curve would have no negative class, and §3.2 would measure nothing. The brief also asks
  for the explicit statement, which would be gone.
- **One prompt with a conditional branch.** A model that is told "use the context, but if
  it is insufficient use your own knowledge" answers from memory whenever the context is
  merely inconvenient, which is the failure mode this system exists to prevent.
- **Answer generally but still attach a citation to the best chunk.** That is the
  dishonest version of this feature: it would put a marker on a claim the chunk does not
  support, and containment would catch every one of them — 1 in 138 in the two headline
  cells, and only because the generator was not asked to do this.

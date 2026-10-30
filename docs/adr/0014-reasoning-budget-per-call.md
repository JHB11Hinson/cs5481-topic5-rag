# Reasoning budget is a property of the call, not of the model

Every model call declares its thinking budget. Mechanical calls — contextual prefixes, query rewriting, the JSON-mode judge — pass `reasoning_effort: none`; answer generation keeps the provider default.

This is not tuning, it is a correctness fix with a cost attached. With the default budget a one-sentence prefix request spent 163 reasoning tokens and, inside `max_tokens: 120`, returned an empty content field with `finish_reason: length`. The first warm-up wrote 2,203 empty prefixes into the cache and reported a 100% cache hit rate on the rerun: a silent, complete failure that looked like success. Two fixes came out of it — the budget is explicit, and the prefix cache key includes the effort setting, so a prefix produced under one budget can never be served under another.

## Consequences

Mechanical calls cost roughly a tenth of what they did: 27 completion tokens instead of 194 for the same prefix, measured on the same prompt. Generation keeps deliberation, because citation quality depends on it. The cache key change means the prefix cache starts empty once more, which is the correct response to poisoned content, not a lost investment.

Anything that reads a model response must treat empty content as the failure it is. `docs/PROGRESS.md` records the gateway behaviour so it is not rediscovered.

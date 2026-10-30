# Reproducibility comes from the response cache, not from temperature 0

Every experiment runs with temperature 0 and a SQLite cache of model responses keyed by content hash. The cache is the thing that makes a run repeatable; temperature 0 alone does not.

Measured: two consecutive runs of the same 20 items, same prompt, same model, temperature 0, produced 17 and then 21 claims, with citation precision 0.941 and then 0.905. Nothing in the configuration changed except the token budget of the request, which shifted the sampling. Both runs are internally consistent, and neither is reproducible from the other. A report that claims "same prompt, same settings" while relying on the provider returning identical output would be describing a property the provider does not offer.

Once a response is in the cache, its key covers model, messages, max tokens and temperature, so re-running a configuration replays exactly those bytes and the metrics reproduce to the last decimal. That is what the `run_id` in the report points at, and why `cache_stats.json` records hits and misses: a run with misses is a run whose numbers cannot be reproduced without paying for the same calls again.

## Consequences

Changing any prompt text, token budget, or model invalidates the cache and therefore the comparison: an eighteen-cell matrix where one cell was generated under a different token budget is not a like-for-like comparison. Configuration files pin the token budget alongside the model for that reason. Cost per experiment is bounded by the cache rather than by discipline — re-running the whole matrix to redraw a figure is free, which is what makes the redraw possible at all.

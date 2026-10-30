# Ablations run as configuration, not as branches

Every experiment cell is a configuration file evaluated by one code baseline at one pinned commit. Git branches are for developing features and for freezing a baseline tag, never for expressing "this run had contextual prefixes on and that one did not".

An ablation only means something under ceteris paribus: exactly one thing differs, everything else is byte-identical. Branches break that guarantee the moment two branches drift — a stray dependency bump or a refactor on one side turns a single-variable comparison into a two-variable one, and the reported effect becomes unattributable. Configuration files keep the code constant and make the varying dimension enumerable, diffable, and checkable: a runner reads `configs/<cell>.yaml`, and the set of cells can be listed and validated before any money is spent.

Each run writes an immutable directory, `runs/<run_id>/`, holding the resolved configuration, the git SHA, the corpus snapshot id, model identifiers and versions, the prompt hash, per-question predictions, the metric block, and timings. The report cites `run_id` for every number, so any claim can be traced back and re-executed.

## Consequences

The runner has to exist before the matrix runs, which means writing the harness early even though it feels like overhead on day 2. LLM responses must be cached by `(model, prompt_hash, params)` and embeddings by `(model, chunk_hash)`, or reruns cost money and drift. Large artifacts — the vector store, the extracted text, the model weights — stay out of git behind a checksummed download script; the small JSON results go in.

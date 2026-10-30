# 12: The eighteen-cell matrix runs unattended

**What to build:** all eighteen configurations — two chunk strategies, three retrieval modes, three contextualization levels — are emitted from one grid definition and executed by a resumable runner that skips finished cells, survives a crash, and degrades to a valid twelve-cell matrix if late chunking is not ready.

**Blocked by:** 07, 09, 10, 11.

**Status:** ready-for-human — grid emitted, checked and projected; the paid overnight run is what is left

`ragqa/grid.py` holds one declaration: `BASELINE` plus three level tables, from which `emit()` writes `configs/grid/cell-<chunk>-<retrieval>-<context>.yaml` (18 files) and `grid.json` (schema `ragqa.grid/1`). Every cell is the full-strength configuration — Vault snapshot, bge-m3 on cuda, Qdrant, the hosted generator, `k=10` — so two cells differ only in their three factor levels; that invariant is asserted in `tests/test_grid.py`, not commented. The one deliberate bundle: a retrieval level carries the abstention threshold for its own score scale (cosine / RRF / cross-encoder logits), because a shared threshold would be wrong for two of the three modes.

Projection: 18 cells x 60 items = 1,080 generation calls, matching spec row 1 exactly (the guard allows 5% and treats a miss as a grid bug). The degraded design, `python -c "from ragqa import grid; grid.emit(exclude=['late_chunking'])"`, is 12 cells x 60 = 720, against ADR-0006's 720.

A run directory counts as finished when `<out_root>/*/metrics.json` exists for a directory whose resolved `config.json` hashes to the cell's config digest — the wall-clock stamp in the run id is ignored, which is what makes resume work. `--force` re-runs everything, `--dry-run` prints order, per-cell item counts and the projected total without touching the money.

Remaining for the human: `python -m ragqa grid run` overnight once `golden/v1.jsonl` (ticket 08) and the gateway key exist, then `ragqa aggregate` against `configs/grid/grid.json`.

- [x] `ragqa grid --emit` generates all 18 configs from one declaration; cell names encode their factors
- [x] `ragqa grid --check` validates every config and prints the cell table before anything runs
- [x] The runner skips cells with an existing metrics file and resumes; `--force` overrides
- [x] `--dry-run` prints run order, item counts, and projected generation calls without spending money
- [x] Projected calls match the inventory within 5%; a mismatch is treated as a grid bug
- [x] The degradation switch produces a complete 12-cell matrix when late chunking is excluded
- [ ] The full matrix completes overnight and every cell has a run directory

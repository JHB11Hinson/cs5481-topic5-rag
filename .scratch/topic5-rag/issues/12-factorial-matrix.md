# 12: The eighteen-cell matrix runs unattended

**What to build:** all eighteen configurations — two chunk strategies, three retrieval modes, three contextualization levels — are emitted from one grid definition and executed by a resumable runner that skips finished cells, survives a crash, and degrades to a valid twelve-cell matrix if late chunking is not ready.

**Blocked by:** 07, 09, 10, 11.

**Status:** ready-for-agent

- [ ] `ragqa grid --emit` generates all 18 configs from one declaration; cell names encode their factors
- [ ] `ragqa grid --check` validates every config and prints the cell table before anything runs
- [ ] The runner skips cells with an existing metrics file and resumes; `--force` overrides
- [ ] `--dry-run` prints run order, item counts, and projected generation calls without spending money
- [ ] Projected calls match the inventory within 5%; a mismatch is treated as a grid bug
- [ ] The degradation switch produces a complete 12-cell matrix when late chunking is excluded
- [ ] The full matrix completes overnight and every cell has a run directory

# 01: Smoke path end to end on stub inputs

**What to build:** `python -m ragqa.run --config configs/smoke.yaml` walks the entire pipeline — load a fixture corpus, chunk it, embed it, index it, retrieve for each golden item, generate an answer with a claim and a citation, verify the citation, score the run — and leaves a complete `runs/<run_id>/` directory. Every model is a deterministic stub, so it needs no network, no GPU, and no API key.

**Blocked by:** None (can start immediately).

**Status:** done

Shipped: `ragqa/{config,contract,corpus,chunk,embed,index,retrieve,generate,verify,evaluate,golden,run,selftest}.py`, `configs/smoke.yaml`, `fixtures/smoke/`, 22 unit tests. Two runs of the same config produce an identical `metrics.json` hash; the abstention path fires on the near-miss fixture item.

- [x] `configs/smoke.yaml` runs in under 60 seconds and exits 0
- [x] Run directory contains config, git state, corpus snapshot, models, metrics, predictions, citations, timings, errors, cache stats
- [x] Unknown config keys are rejected with a message naming the key
- [x] Two consecutive runs produce byte-identical `metrics.json`
- [x] `python -m ragqa.selftest` runs the unit tests and exits non-zero on failure

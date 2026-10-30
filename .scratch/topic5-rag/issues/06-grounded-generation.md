# 06: Grounded generation with machine-checkable claims

**What to build:** a real generator answers from retrieved chunks and returns structured claims, each carrying doc id, chunk id, and character offsets into that chunk, plus an explicit abstention when the retrieved evidence is insufficient. A program then checks that every cited span exists inside a chunk that was actually retrieved.

**Blocked by:** 05.

**Status:** done

Shipped: `ragqa/llm.py` and `LLMGenerator` in `ragqa/generate.py`, plus `configs/real_llm.yaml`, `scripts/probe_models.py`, `scripts/inspect_run.py`.

Gateway note that cost an hour: the OpenCode **Go** subscription is a *different base path* from the plain zen catalog — `https://opencode.ai/zen/go/v1`, not `/zen/v1` — and requests must carry an `x-opencode-session` header, or they route to the unfunded catalog and fail with `402 server_error: Upstream request failed`. Both facts came from the harness's own provider definition (`@earendil-works/pi-ai/dist/providers/opencode-go.js`) rather than from guesswork. `llm.session_header` / `llm.session_id` now carry it.

Design change: the model is asked for a verbatim `quote` per claim, **not** character offsets. A model cannot count characters, and a wrong offset would make a true citation look false; `verify.check_claims` derives the span by string search and a quote that does not occur becomes its own class, `quote_not_in_chunk`. That class fired twice in practice, including one invented quote about a `secret/` mount in a document that never says it.

Measured on golden v0, rerank retrieval, `deepseek-v4.1-flash`, temperature 0, 20 items:

| metric | run 1 (budget 900) | run 2 (budget 1600) |
|---|---|---|
| citation precision | 0.941 | 0.905 |
| citation recall | 0.900 | 0.900 |
| span hit rate | 0.588 | 0.429 |
| abstention on near-misses | 9/10 | 9/10 |
| over-abstention | 0.000 | 0.000 |
| claims emitted | 17 | 21 |
| cost | $0.030 | $0.036 |
| ¥ per 1,000 questions | 10.0 | 12.0 |

The two runs differ because temperature 0 does not guarantee identical output; the response cache is what makes a run reproducible (`ADR-0012`).

- [x] `generate.provider: llm` emits `predictions.jsonl` with answer text, claims, citations, abstained flag, token counts, latency
- [x] Claim offsets are relative to retrieved chunk text, never to the answer text
- [x] Schema violations are counted as `parse_failure`, retried once with a corrective message, and their rate is reported per configuration
- [x] The abstention path exists and its trigger reason is recorded
- [x] Containment check classifies failures as `chunk_not_retrieved`, `quote_not_in_chunk`, `span_out_of_bounds`, or `span_text_mismatch`, and the catch rate is reported separately from judge-scored precision
- [x] Prompt files are versioned and their hash appears in the run directory
- [x] A configuration produces real answers against golden v0
# Golden QA Set — field specification

One JSON object per line, UTF-8, file `golden/v<n>.jsonl`. Version is immutable: a correction produces `v2`, it never edits `v1`. Every reported number names the version it was measured against.

## Answerable item

```json
{
  "id": "A001",
  "answerable": true,
  "type": "fact_lookup",
  "question": "Which setting controls how many background merges can run at once?",
  "reference_answer": "background_pool_size, in the server settings.",
  "evidence": [
    {
      "doc_id": "operations/server-configuration-parameters/settings.md",
      "quote": "background_pool_size — Sets the number of threads performing background merges and mutations for tables with the MergeTree engine."
    }
  ],
  "difficulty": "easy",
  "provenance": { "drafted_by": "llm:deepseek-v3@2026-11-02", "verified_by": "human", "edits": "shortened the question, dropped the engine name" },
  "tags": ["settings", "mergetree"]
}
```

Fields:

| Field | Rule |
|---|---|
| `id` | `A###` for answerable, `U###` for unanswerable. Never reused, never renumbered. |
| `type` | One of `fact_lookup`, `param_value`, `table_content`, `multi_hop`, `concept`. |
| `question` | The question as a user would actually type it. No document-specific jargon that only the docs use. |
| `reference_answer` | One to three sentences. Graded against, so short and checkable beats complete. |
| `evidence` | One or more `{doc_id, quote}`. `quote` is copied verbatim from the document, 1–2 sentences, and long enough to be unique in the corpus. |
| `difficulty` | `easy` / `medium` / `hard` by how many retrieval steps the answer needs, not by how long the answer is. |
| `provenance` | Who drafted it and what the human changed. Required, including when a human wrote it from scratch (`"drafted_by": "human"`). |
| `tags` | Free-form, lowercase, used for slicing the error analysis. |

**`evidence` is anchored by document plus quoted text, never by chunk id.** Chunk ids change with every chunk strategy and every re-chunk; the golden set has to outlive them. A retriever's hit is decided by checking whether any returned chunk contains the quoted span after normalising whitespace.

**`quote` must be unique in the corpus.** If a sentence appears in twelve near-identical pages, the item measures duplicate handling, not retrieval. Check before accepting an item.

## Unanswerable item

```json
{
  "id": "U001",
  "answerable": false,
  "type": "near_miss",
  "question": "What is the default value for the replicated_deduplication_window setting in version 25.8?",
  "why_unanswerable": "The setting exists, but this corpus snapshot documents 25.3 and the question asks for a later release.",
  "near_miss_doc": "operations/settings/settings.md",
  "difficulty": "hard",
  "provenance": { "drafted_by": "human", "verified_by": "human", "edits": "" }
}
```

Rules:

- **Near-miss, not off-topic.** Every unanswerable item must be topically adjacent to something the corpus does cover, with a plausible-looking `near_miss_doc`. Off-topic questions ("who won the 2018 World Cup") measure nothing — the retriever returns noise and any threshold rejects it.
- Good generators of near-misses for this corpus: features from a later/earlier release than the snapshot, operational questions about the user's own deployment, questions whose answer lives in a sibling product's docs, "how do I configure X and Y together" where the combination is not documented.
- `why_unanswerable` must be checkable by a second person in under a minute.

## Strata quotas (v1, 60 items)

| Stratum | Answerable | Unanswerable |
|---|---|---|
| `fact_lookup` | 10 | — |
| `param_value` | 8 | — |
| `table_content` | 8 | — |
| `multi_hop` | 8 | — |
| `concept` | 6 | — |
| `near_miss` | — | 20 |
| **Total** | **40** | **20** |

`multi_hop` items name two `evidence` entries from two distinct `doc_id`s. `table_content` items require the answer to come from a table row, and are the items most likely to break under naive chunking — that is their purpose.

## Validation

`python -m ragqa.golden validate golden/v1.jsonl` must check, and fail loudly on:

1. schema conformance and unique `id`s
2. quota counts match the table above
3. every `doc_id` exists in the corpus snapshot
4. every `quote` appears in its document after whitespace normalisation
5. every `quote` is unique within the corpus (report duplicates with their locations)
6. no question text shorter than 15 characters or longer than 400

## Build passes

- **v0, 20 items (10 answerable + 10 unanswerable)** — exists before the first end-to-end run. Cheap, thrown away later; its only job is to let the harness run.
- **v1, 60 items** — the set every reported number uses. Drafted with an LLM, then every item opened against the document by a human. Items where the human changed the question materially get `edits` filled in; the count of those is reported.

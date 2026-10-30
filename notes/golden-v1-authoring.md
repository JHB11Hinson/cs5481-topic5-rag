# Golden set v1 — how it was authored

`golden/v1.jsonl` is the 60-item set every reported number is measured against
(ADR-0005). It supersedes `golden/v0.jsonl` as the set experiments consume; v0 stays
on disk unchanged because a version is immutable.

## What is in it

| Stratum | Count | Difficulty spread |
|---|---|---|
| `fact_lookup` | 10 | easy 4, medium 6 |
| `param_value` | 8 | easy 2, medium 6 |
| `table_content` | 8 | medium 5, hard 3 |
| `multi_hop` | 8 | hard 8 |
| `concept` | 6 | medium 6 |
| **answerable total** | **40** | easy 6, medium 23, hard 11 |
| `near_miss` (unanswerable) | 20 | easy 4, medium 11, hard 5 |
| **total** | **60** | easy 10, medium 33, hard 17 |

Ids are allocated in stratum order: `A001`–`A010` fact lookup, `A011`–`A018` parameter
values, `A019`–`A026` table content, `A027`–`A034` multi-hop, `A035`–`A040` concept,
`U001`–`U020` near-misses. A reader can therefore tell an item's stratum from its id,
which v0's mixed numbering did not allow.

Every answerable item satisfies the two structural promises in `golden/SPEC.md` that
the validator cannot check: `table_content` quotes are table rows (they contain pipes
and resolve in `mode="line"`), and `multi_hop` items carry two evidence entries with
two distinct `doc_id`s. `tests/test_golden_v1.py` enforces both, so a future edit
cannot quietly break them.

## Where the quotes come from

`golden/spec_v1.json` holds no quote text. Each piece of evidence is a
`(doc_id, keyword)` pair plus an extraction mode, and `scripts/golden_emit.py` copies
the sentence or table row out of the corpus snapshot. Nothing in this set was typed
from memory: hand-typing is the one defect that turns a "verbatim quote" check into a
check of the author's typing.

The emit command used:

```
python scripts/golden_emit.py golden/spec_v1.json golden/v1.jsonl \
  --corpus=".../vault-1.21.x-1817bdfe/docs_structured.jsonl" \
  --drafted-by="llm:deepseek-v4.1-flash@2026-10-30"
```

Quotes were chosen to be complete sentences wherever the documentation wraps them
that way. Where the source is hard-wrapped mid-sentence, the item was re-anchored to a
line that survives extraction as a grammatical sentence rather than accepting a
truncated fragment; that is why `v0`'s dev-mode `kv` item and its cert auto-auth
`reload` item (both quoted a cut-off list item) are not carried into v1.

## Drafting model, date, and what "verified" means

- Drafted by `llm:deepseek-v4.1-flash@2026-10-30`. The model proposed the questions,
  the reference answers, and the evidence anchors.
- `verified_by` is `automated:corpus-anchored` on all 60 items. **No human opened these
  items against the documents.** The honest claim is: every quote was proven to appear
  verbatim and exactly once in the corpus by the validator, and every question was
  written from a sentence that was read in its document context. That is weaker than a
  human review of grading behaviour and should be described that way in the report.
- `provenance.edits` is empty on every item, because no human edit happened; the
  machine-side revisions below are recorded here instead of being dressed up as human
  edits.

## Revisions after the first emit

Six items changed between the first draft and the file that ships.

Before the first successful emit (the emit aborted, so nothing was written):

1. `A038` — the token-tree concept item anchored on a sentence that only exists split
   across two source lines, so the keyword never resolved. Replaced with the
   key-per-purpose item from `docs/internals/rotation`.

After the first successful emit, found by reading all 49 extracted quotes next to their
source lines:

2. `A022` — the anchor resolved to the heading `## Rate limit quotas` instead of the
   table row underneath it (validation passed: a heading is verbatim in its document).
   Re-anchored to the row's unique text.
3. `A028` — the auto-unseal evidence resolved to a line fragment beginning
   "initializing operations with auto unseal yields recovery keys." Re-anchored to a
   complete sentence on the same page.
4. `U015` — originally "can I enable seal HA and run a seal migration at the same
   time?". This is **answerable**: `docs/concepts/seal` states that seal HA is the
   supported online migration path for auto seals. Replaced with the
   response-wrapping-token-during-seal-migration question, which no page answers.
5. `U016` — originally "rekey the unseal keys and rotate the backend key in one
   window". `docs/internals/rotation` lists rekey then rotation as consecutive steps,
   which a reader can turn into an answer. Replaced with the namespace-API-lock versus
   Sentinel-EGP question.
6. `U011` — `near_miss_doc` pointed at `docs/agent-and-proxy/injector`, which is not a
   document in this snapshot. Corrected to `docs/deploy/kubernetes/injector`.

## The five near-miss generators

Four items each, all topically adjacent to a page the corpus does contain, so a
retriever returns plausible context and only a working abstention path rejects them.

| Generator | Items | How absence was checked |
|---|---|---|
| Later release than the snapshot | `U001`–`U004` | `shed_rate` and `disable_gzip` occur 0 times in the corpus; `replication_primary` is documented but never with the release that introduced it; the `-dev-kv-v1` flag is documented as current, with no removal recorded |
| Deployment-specific state | `U005`–`U008` | These ask for live state (unseal threshold, secondary count, image digest, raft log size); the corpus describes mechanisms and defaults, and contains no digests or cluster sizes |
| Sibling product's documentation | `U009`–`U012` | "catalog sync", "consul intentions" and `vault_kv_secret_v2` occur 0 times; "admission controller" appears once, only as a description of the injector's own controller, never as one to disable |
| Undocumented combination | `U013`–`U016` | AppRole `secret_id_ttl` and agent token TTL are documented apart and never composed; only the Consul→Integrated-Storage migration direction exists; the seal page never mentions response-wrapping and the wrapping page never mentions migration; the API-lock page never mentions Sentinel and the Sentinel pages never mention the lock |
| Commercial-only | `U017`–`U020` | No price, seat count, SLA percentage or tier name ("Essentials", "per-seat") occurs in the corpus; the one pricing sentence says client totals are the pricing basis without figures |

Every `near_miss_doc` names a document that exists in the snapshot, so the metadata
does not leak that the item is unanswerable.

## One defect found in v0 (v0 is immutable, so it stays wrong)

v0's `U005` asks for "the Terraform resource name for the Vault AWS auth backend" and
asserts the corpus never names Terraform resources. It does:
`docs/deploy/kubernetes/vso/sources/vault/auth/aws` shows
`resource "vault_aws_auth_backend_role"`. That v0 item is at least partly answerable.
v1 does not carry it; the sibling-product slots were rebuilt on terms with zero corpus
occurrences. Fixing v0 would need a `v2`, per the immutability rule.

## How this was verified

```
$ python scripts/golden_emit.py golden/spec_v1.json golden/v1.jsonl \
    --corpus="D:\DE Project\Project\data\corpus\vault-1.21.x-1817bdfe\docs_structured.jsonl" \
    --drafted-by="llm:deepseek-v4.1-flash@2026-10-30"
wrote 60 items to golden/v1.jsonl

$ python -m ragqa golden validate golden/v1.jsonl --strict-quotas \
    --corpus="D:\DE Project\Project\data\corpus\vault-1.21.x-1817bdfe\docs_structured.jsonl"
golden/v1.jsonl: ok against 1268 documents
$ echo $?
0
```

The validator checks schema, unique ids, the quota table, `doc_id` existence,
quote-verbatim after whitespace normalisation, quote uniqueness across the whole
corpus, and question length. All 49 evidence quotes are distinct from one another as
well, so no two items share an anchor.

`python -m ragqa.selftest` runs 58 tests green, including
`tests/test_golden_v1.py`, which proves the validator rejects a quote that drifted from
its document and a quote that is not unique, and that v1 meets the quota table, the
table-row and two-document rules, and the provenance fields. That last test's
corpus-anchored case needs the snapshot present; the worktree does not have it, so the
same test is run with `RAGQA_CORPUS` pointed at the shared checkout, and it is a no-op
where the snapshot is absent.

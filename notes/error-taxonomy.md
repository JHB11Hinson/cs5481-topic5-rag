# Error taxonomy

Nine fixed failure classes, and every failure the finished matrix cells contain, assigned to
exactly one of them. The classes were fixed before the runs were inspected; the assignments come
from reading the claim, the cited chunk and the retrieved list, not from the strings in
`errors.jsonl`.

## How the material was assembled

`ragqa.aggregate.failure_candidates()` walks every finished `grid-*` run directory and collects,
per item: the golden evidence (document and quote), the retrieved list with ranks and scores, the
chunks that were actually in the generator's context window, the abstention decision, and every
verification verdict. `.scratch/topic5-rag/inspect_failures.py` dumps that to JSON, and the table
below was written by reading the dump. The command is repeatable, so when the remaining cells
finish the same extraction finds their failures:

```
python .scratch/topic5-rag/inspect_failures.py "D:\DE Project\wt\exp\runs" failures.json
```

`errors.jsonl` is not used to classify anything. It only ever carries the containment layer's own
strings (`quote_not_in_chunk`, `span_out_of_bounds`, `span_text_mismatch`, `chunk_not_retrieved`)
plus `parse_failure`; a class that a reader would care about — "the right document, the wrong
chunk" — never appears there.

## The nine classes

A failure is assigned by **the earliest layer that lost the answer**, so the same event is never
counted twice. When a retrieval miss makes the generator abstain, the row is the retrieval class
and the abstention is recorded as its symptom in the justification.

| # | class | definition | how it is decided from the artifacts |
|---|---|---|---|
| 1 | `retrieval-document-miss` | No chunk of any evidence document reached the returned depth: the passage was never a candidate. | the item is in `metrics.json` `retrieval.misses` **and** no evidence `doc_id` appears in `predictions.jsonl` `retrieved[]` |
| 2 | `retrieval-chunk-miss` | The evidence document was retrieved, but no returned chunk contains the evidence quote — the passage was split into a sibling chunk or into a parent that was not expanded. | miss as above, but at least one evidence `doc_id` is in `retrieved[]`; normalised quote absent from every returned chunk text |
| 3 | `context-budget-drop` | The quote-bearing chunk was retrieved at a rank beyond `llm.context_chunks`, so it never entered the prompt. | quote-bearing chunk not in context, its rank > `llm.context_chunks` from the run's `config.json` |
| 4 | `generator-over-abstention` | The generator refused a question it had the evidence for. | `abstained` true on an answerable item whose quote-bearing chunk is in the context window, with a non-empty `abstain_reason` |
| 5 | `generator-under-abstention` | The generator answered a near-miss of the knowledge base from neighbouring documentation. | `abstained` false on an item with `answerable` false |
| 6 | `citation-quote-not-in-chunk` | The claim's quoted span does not occur in the chunk it is cited against: the citation is fabricated at the span level. | `citations.jsonl` `error_class = quote_not_in_chunk`; the quote is absent from the chunk text under whitespace normalisation |
| 7 | `citation-span-out-of-bounds` | The quoted text does occur, but the reported offsets do not delimit it. | `error_class` in `{span_out_of_bounds, span_text_mismatch}` |
| 8 | `citation-chunk-not-retrieved` | The claim cites a chunk id that was never in the retrieved set. | `error_class = chunk_not_retrieved` |
| 9 | `generation-parse-failure` | The response could not be parsed into claims, so the item produced no verdict at all. | `errors.jsonl` `class = parse_failure`, with the raw response inspected |

Classes 5, 7 and 8 have no instance in the runs that were finished when this was written. They stay
in the taxonomy because a class list that only contains what happened cannot tell a reader what was
looked for and was absent.

## The assigned failures

Each row names the run it came from. `dense-plain-…8ae4eb06` is
`cell-fixed-dense-plain`, `hybrid-plain-…6170ae66` is `cell-fixed-hybrid-plain`.

| # | run id | item | class | the claim (or the claim that was never made) | justification |
|---|---|---|---|---|---|
| 1 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A003 | `retrieval-document-miss` | reference: "an unseal key"; the run said "the provided context does not state what is required" | evidence doc `docs/commands/operator/init` is absent from all ten returned chunks; the top three are PKI root-CA, `system/rotate`, `generate-root-token`, so "root key" pulled the ranker into the wrong subtree |
| 2 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A010 | `retrieval-chunk-miss` | reference: "reauthenticate and obtain new leases from the newly promoted primary" | `docs/enterprise/replication` is returned at ranks 1 and 6, yet neither chunk contains the quoted sentence: the failover paragraph lives in a chunk the splitter put elsewhere |
| 3 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A016 | `retrieval-document-miss` | reference: "2 days"; the run said the option is not mentioned | `docs/configuration` — a parent of the option's page — is not retrieved; the top three are transit/leases/lease-count-quotas, so an option name with an underscore behaved like an opaque token |
| 4 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A030 | `retrieval-chunk-miss` | reference: "remounting revokes existing leases, and every dynamic secret carries a lease" | `docs/concepts/mount-migration` is at rank 4 but the revoking sentence is not in that chunk; the evidence for the second half (`docs/concepts/lease`) never appears at all |
| 5 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A035 | `retrieval-document-miss` | reference: "so the key stored with the data is itself protected by the root key"; the run abstained | `docs/concepts/seal` is absent; three of the returned docs are `about-vault` overview pages whose prose restates the question without the mechanism |
| 6 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A037 | `retrieval-document-miss` | reference: "it can eventually cause serious issues with the underlying storage, and then with Vault itself" | `docs/concepts/tune-server-performance` is absent; the returned `prevent-lease-explosions` page discusses the same risk but the golden quote is matched only against the tuned-performance page |
| 7 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A015 | `generator-over-abstention` | reference: "131072 entries"; the run abstained, saying nothing in the context gives a default count | this item is **not** a retrieval miss: the quote-bearing chunk was in context. The generator refused anyway — the chunk states the default as a bare `**131072**` under a heading it evidently did not connect to "storage read cache" |
| 8 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | A031 | `generation-parse-failure` | raw response opens `{"answerable": true, "claims": [{"text": "With Consul storage, the 512KB cap applies to …"` and then stops being parseable | the model produced the right fact and the contract layer could not read the envelope; this is the only error class the run recorded, and it is a generation-format failure, not a grounding one |
| 9 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A015 | `retrieval-chunk-miss` | reference: "131072 entries" | `docs/concepts/tune-server-performance` is returned at rank 7, inside the context window, but the quote is not in that chunk: the cache-table row was split into a neighbouring chunk of the same page |
| 10 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A030 | `retrieval-chunk-miss` | reference: "remounting revokes existing leases…" | same item as row 4, different ranker: `docs/concepts/mount-migration` at rank 8, again without the revoking sentence; fusion moved the page up but did not move the passage in |
| 11 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A035 | `retrieval-document-miss` | reference: "so the key stored with the data is itself protected by the root key" | `docs/concepts/seal` absent again, with a different top ten (`secrets/transit`, `why-use-vault`, `what-is-vault`): the same conceptual gap survives the ranker swap |
| 12 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A038 | `retrieval-document-miss` | reference: "it stores different keys for different purposes, so rotation targets the key that needs changing" | `docs/internals/rotation` is not retrieved; the top three are overview pages whose single sentence "Vault stores different encryption keys for different purposes" is the golden quote's paraphrase, so the surface match was satisfied by a page that cannot support the "why" |
| 13 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A031 | `generator-over-abstention` | the answer the run should have made: archived versions of one key must share a single 512KB storage entry | both evidence chunks were retrieved and the generator still abstained, quoting the Consul cap and then judging it insufficient — the failure is the join between two retrieved passages, not retrieval |
| 14 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | A032 | `citation-quote-not-in-chunk` | claim A032-c2: "Entity aliases let clients authenticate with multiple methods but still be associated with…" | the cited chunk defines *client*; the alias sentence is in `docs/concepts/identity`, a document that was not retrieved. The model wrote a correct-sounding claim and attached a citation it had not read (span `-1`, so it also had no span to offer) |

## Counts per class per cell

| class | `cell-fixed-dense-plain` | `cell-fixed-hybrid-plain` | total |
|---|---|---|---|
| `retrieval-document-miss` | 4 | 2 | 6 |
| `retrieval-chunk-miss` | 2 | 2 | 4 |
| `context-budget-drop` | 0 | 0 | 0 |
| `generator-over-abstention` | 1 | 1 | 2 |
| `generator-under-abstention` | 0 | 0 | 0 |
| `citation-quote-not-in-chunk` | 0 | 1 | 1 |
| `citation-span-out-of-bounds` | 0 | 0 | 0 |
| `citation-chunk-not-retrieved` | 0 | 0 | 0 |
| `generation-parse-failure` | 1 | 0 | 1 |
| **total** | **8** | **6** | **14** |

## Shortfall: 14 of the 40, and where the other 26 are

The ticket asks for 40 hand-inspected failures. When this note was written, **two of the eighteen
cells had finished** (`cell-fixed-dense-plain`, `cell-fixed-hybrid-plain`), a third
(`cell-fixed-rerank-plain`) had a directory with no `metrics.json` — not a run — and fifteen cells
had produced nothing. The two finished runs contain 18 failure candidates, which collapse to the 14
distinct failures above once an abstention is counted as the symptom of the retrieval miss that
caused it rather than as a second failure. That is a shortfall of **26**, and it is not padded:
inventing rows would defeat the point of a taxonomy that is supposed to describe what the system
actually does.

The remaining cells are still executing in `D:\DE Project\wt\exp\runs`, and each finished cell
contributes roughly 6–9 new failures at the current rates (about 0.15 retrieval failures and 0.05
abstention failures per question). Five or six more cells would carry the total past 40. To finish
the note, re-run the extraction command above and append rows; the nine classes are fixed and need
no revision to absorb them.

One class is expected to stay empty: `context-budget-drop` needs a quote-bearing chunk at a rank
above `llm.context_chunks` (8) while `retrieval.k` is 10, so it can only appear when a hit lands at
rank 9 or 10 — none did in these two cells. If it stays empty after all eighteen, the honest
conclusion is that the context window is wide enough that the k → context narrowing never bites,
which is worth one sentence in the report rather than a row in this table.

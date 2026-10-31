# Error taxonomy

Nine fixed failure classes, and every observable failure in the eighteen finished matrix cells
assigned to exactly one of them. The classes were fixed before the runs were inspected and their
names and definitions do not change here; the assignments come from reading the question, the
reference answer, the generated answer and the cited span, not from the strings in `errors.jsonl`.

All eighteen cells have now finished: **275 failures**, of which **40 were hand-inspected** for this
note. Where the note is confident about a class and not about a mechanism inside it, it says so.

## What changed since the two-cell version

The previous version of this note classified 14 failures from the two cells that had finished. The
class names and the definitions below are the same nine; three things are new.

1. **The counting unit is written down.** An event is one `(item, layer)` pair: an item can fail
   retrieval *and* carry a rejected claim, and those are different defects with different fixes. The
   precedence rule below keeps the item-level count from double-counting a single lost answer.
2. **Every gold quote, not any gold quote.** The run's own hit@10 is any-of: `evaluate._first_hit_rank`
   returns on the first evidence quote it locates. A multi-hop item therefore counts as a retrieval
   hit with one of its two legs missing, and the two-cell note was reading those as hits. The
   taxonomy now requires *every* gold quote to be placed before it clears retrieval -- 56 of the 196
   evidence-loss events below are items the matrix counted as hits.
3. **One earlier assignment was wrong, and one forecast was wrong.** `A015` in
   `cell-fixed-dense-plain` was filed as `generator-over-abstention`; re-reading the ranks shows the
   quote-bearing chunk at rank 9 against a window of 8, so it is `context-budget-drop`. The two-cell
   note also guessed that `context-budget-drop` would stay empty; it fires 29 times.

**A tenth class is not needed.** The one place the nine felt too coarse -- 26 rejected quotes all
landing in `citation-quote-not-in-chunk` -- turned out to be four mechanisms inside one class (see the
last section). Splitting the class would have described the same 26 events as four names without
telling a reader anything new about which component to fix.

## The nine classes

A failure is assigned by **the earliest layer that lost the answer**, so the same lost answer is
never counted twice. When an evidence miss makes the generator abstain, the row is the retrieval
class and the abstention is recorded as its symptom in the justification.

| # | class | definition | how it is decided from the artifacts |
|---|---|---|---|
| 1 | `retrieval-document-miss` | No chunk of any evidence document reached the returned depth: the passage was never a candidate. | the item's gold quote is in no returned chunk, and at least one gold evidence `doc_id` is absent from `retrieved[]` |
| 2 | `retrieval-chunk-miss` | The evidence document was retrieved, but no returned chunk contains the evidence quote -- the passage was split into a sibling chunk, or into a parent that was not expanded. | the gold quote is in no returned chunk, while every gold evidence `doc_id` is in `retrieved[]` |
| 3 | `context-budget-drop` | Every retrieved chunk carrying the quote sits beyond `llm.context_chunks`, so the passage never entered the prompt. | the quote-bearing chunk's rank exceeds the run's own `config.json` `llm.context_chunks` |
| 4 | `generator-over-abstention` | The generator refused an answerable question with the whole evidence set inside its context window. | abstained on an answerable item whose every gold quote sits at a rank within `llm.context_chunks` |
| 5 | `generator-under-abstention` | The generator answered a question the knowledge base does not answer, from neighbouring documentation. | not abstained on an item whose golden `answerable` flag is false |
| 6 | `citation-quote-not-in-chunk` | The claim's quoted span does not occur in the chunk it is cited against: a fabricated, spliced or mangled span. | `citations.jsonl` `error_class = quote_not_in_chunk`, re-checked by locating the quote in the rebuilt chunk text |
| 7 | `citation-span-out-of-bounds` | The quoted text does occur, but the reported offsets do not delimit it. | `error_class` in {`span_out_of_bounds`, `span_text_mismatch`} |
| 8 | `citation-chunk-not-retrieved` | The claim cites a chunk id that was never in the retrieved set. | `error_class = chunk_not_retrieved` |
| 9 | `generation-parse-failure` | The response could not be parsed into claims, so the item produced no verdict at all. | `errors.jsonl` `class = parse_failure`, with `tokens_out` and the raw response inspected |

## How the material was assembled

`ragqa.aggregate.failure_candidates()` walks the eighteen finished `grid-*` directories and collects,
per item, the golden evidence, the retrieved list with ranks and scores, the abstention decision and
every verification verdict in `citations.jsonl`. `.scratch/topic5-rag/inspect_failures.py` dumps that
to JSON and is still the way to find the same failures again.

`chunks.jsonl` is excluded from git, so the chunk text every containment check needs was rebuilt
**in memory** by calling `ragqa.chunk.build` with each run's own `chunk.strategy` / `size` /
`overlap` / `parent_size` on the committed corpus (`data/corpus/vault-1.21.x-1817bdfe`, gitignored,
read from the parent checkout). **No run directory was written to.** The rebuild is verified, not
assumed: every `chunk_id` in every `predictions.jsonl` of all eighteen cells resolves against it --
0 unresolved ids -- so the text checked is the text the generator was given.

For the three `contextual_prefix` cells the rebuild carries the chunk body without the generated
prefix sentence. A prefix can only add text, so a quote found in the rebuild was certainly in the
run's chunk: the check is conservative there, and a quote carried only by a prefix would show up as a
false miss. No such case was found; those cells classify consistently with their `plain` siblings.

`errors.jsonl` is still not used to classify anything. It carries only the containment layer's own
strings plus `parse_failure`, and the interesting class -- "the right document, the wrong chunk" --
never appears there.

## How the forty were sampled

The sample is **stratified for coverage, not for rate estimation**: the per-class counts below come
from all 275 events, and the forty exist to show what each firing class looks like. Each class got a
fixed quota, then events were drawn round-robin over cells in run-id order, one per cell per pass,
preferring an item the sample had not used yet so the forty cover distinct questions rather than one
repeated question:

| class | events available | sampled |
|---|---|---|
| `retrieval-document-miss` | 157 | 18 |
| `retrieval-chunk-miss` | 39 | 6 |
| `context-budget-drop` | 29 | 5 |
| `citation-quote-not-in-chunk` | 26 | 6 |
| `generation-parse-failure` | 17 | 3 |
| `citation-chunk-not-retrieved` | 7 | 2 |
| `generator-over-abstention` | 0 | 0 |
| `generator-under-abstention` | 0 | 0 |
| `citation-span-out-of-bounds` | 0 | 0 |

The draw covers **18 of 18 cells and 19 distinct items**. The two classes with no event cannot be
sampled, which is itself the result reported below.

## The forty failures

Each row names the run it came from, so the reader can open `runs/<run id>/predictions.jsonl` and
check the claim. `--` separates the observation from what it means.

| # | run id | item | class | justification |
|---|---|---|---|---|
| 1 | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | `A003` | `retrieval-document-miss` | `docs/commands/operator/init`, the page that says 'requires an _unseal key_ to decrypt it', is in none of the ten chunks; the returned set is `system/rotate`, `pki/quick-start-root-ca` and `generate-root`, and `docs/concepts/seal` appears only at rank 9, outside the eight-chunk window. |
| 2 | `grid-fixed-dense-late_chunking-20261030T161040-76813f02` | `A001` | `retrieval-document-miss` | `docs/concepts/seal` is absent; the ranker read 'what state does a server start in' as a dev-server question (`dev-server`, `run-as-service`, `ui`) and the generator answered from that page -- 'starts automatically initialized and unsealed' -- the opposite of the reference's sealed state. |
| 3 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | `A003` | `retrieval-document-miss` | same item and same missing page as row 1; here the generator abstained instead of answering from memory, which is the abstention the miss causes -- the cause is the absent `docs/commands/operator/init`, not the abstention policy. |
| 4 | `grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` is returned four times and carries the recovery-key half, but the second evidence page `docs/configuration/seal/seal-best-practices` is absent, and the answer says 'generating a root token' where the reference says 'generating new root keys' -- the distinction only the missing page draws. |
| 5 | `grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39` | `A013` | `retrieval-document-miss` | `docs/internals/recommended-patterns` is absent and the top ten are lease telemetry partials plus `lease/renew` and `lease/lookup`, none of which states a default TTL; the 32 days in the answer has no supporting chunk. |
| 6 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at ranks 1 and 8, `seal-best-practices` absent; the answer again substitutes 'generating a root token' for 'generating new root keys', so one page gap reappears as the same answer error under a different ranker. |
| 7 | `grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222` | `A028` | `retrieval-document-miss` | reranking lifts `docs/concepts/seal` to ranks 1 and 2 and still never returns `seal-best-practices`: the missing page survives a change of ranker, which points at coverage of the question rather than at ordering. |
| 8 | `grid-fixed-rerank-late_chunking-20261030T163138-8f5d6ac0` | `A013` | `retrieval-document-miss` | `docs/internals/recommended-patterns` absent again; the answer keeps 32 days and drops the '768 hours' form the reference pairs with it, and no returned chunk states either value. |
| 9 | `grid-fixed-rerank-plain-20261030T125648-57be667d` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at ranks 1 and 4, `seal-best-practices` absent, answer again 'generating a root token': third cell family, same page, same substitution. |
| 10 | `grid-recursive_parent_child-dense-contextual_prefix-20261030T150403-7ace3fb3` | `A016` | `retrieval-document-miss` | `docs/configuration` is absent and all ten chunks are lease API or concept pages, so an option named `remove_irrevocable_lease_after` never appears; the abstention is correct behaviour for this context and the wrong answer for the corpus. |
| 11 | `grid-recursive_parent_child-dense-late_chunking-20261030T164237-9b6dc31d` | `A001` | `retrieval-document-miss` | same returned set as row 2 (`dev-server`, `run-as-service`, `ui`) with `docs/concepts/seal` absent: parent-child chunking changed the chunk shape and not the candidate set, so the answer describes dev mode again. |
| 12 | `grid-recursive_parent_child-dense-plain-20261030T132126-5b0e5d3e` | `A003` | `retrieval-document-miss` | `docs/commands/operator/init` absent; this cell answered 'the HSM is needed to decrypt it' from `docs/enterprise/hsm` at rank 7 -- a different mechanism, and the citation trail holds no chunk with the gold sentence. |
| 13 | `grid-recursive_parent_child-hybrid-contextual_prefix-20261030T151148-effcbe64` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at rank 1 only, `seal-best-practices` absent; the answer's second half is built from the seal page alone and again names a root token rather than new root keys. |
| 14 | `grid-recursive_parent_child-hybrid-late_chunking-20261030T165835-0cecad68` | `A015` | `retrieval-document-miss` | `docs/concepts/tune-server-performance` is absent -- the ten chunks are agent and proxy caching pages -- yet the answer gives 131,072: the number is right and the evidence trail is empty, which is the failure this class exists to catch. |
| 15 | `grid-recursive_parent_child-hybrid-plain-20261030T133329-e4e09d4e` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at rank 1, `seal-best-practices` absent; A028 fails this way in nearly every cell it appears in, so this is one page-coverage gap reproduced across the matrix, not independent generator errors. |
| 16 | `grid-recursive_parent_child-rerank-contextual_prefix-20261030T152204-d112558a` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at rank 1 and no `seal-best-practices`; 'operations besides unsealing that require a quorum' is assembled from the seal page, without the page that names the privileged actions. |
| 17 | `grid-recursive_parent_child-rerank-late_chunking-20261030T170813-ddf8886b` | `A015` | `retrieval-document-miss` | `tune-server-performance` absent, ten agent and proxy caching chunks returned, and the answer states 131072 with nothing retrieved to support it. |
| 18 | `grid-recursive_parent_child-rerank-plain-20261030T133556-dc28d910` | `A028` | `retrieval-document-miss` | `docs/concepts/seal` at rank 1, `seal-best-practices` absent; eighth instance of this page gap in the sample, with the same 'root token' substitution in the answer. |
| 19 | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | `A010` | `retrieval-chunk-miss` | `docs/enterprise/replication` is returned at ranks 5 and 6 and neither chunk contains 'applications must reauthenticate and obtain new leases from the newly-promoted primary'; the generator abstained saying the context only covers switching clusters, so the page arrived and the paragraph did not. |
| 20 | `grid-fixed-dense-late_chunking-20261030T161040-76813f02` | `A005` | `retrieval-chunk-miss` | `docs/concepts/tokens` is returned only at rank 10 and that chunk does not carry 'Tokens have a specific prefix that indicates their type'; ranks 1-9 are token telemetry partials, so the abstention tracks a chunk boundary, not a judgement call. |
| 21 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | `A010` | `retrieval-chunk-miss` | replication at ranks 1 and 6, neither with the promoted-secondary sentence; the generator answered from the neighbouring 're-authenticate if they switch clusters' text -- right conclusion, no returned chunk supports it. |
| 22 | `grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950` | `A031` | `retrieval-chunk-miss` | both evidence pages are returned (`tune-server-performance`, `internals/limits`) and neither chunk carries its quote, so the answer could not have been grounded; the body is also empty because the call spent its whole budget (tokens_out 3200 against max_tokens 1600), the parse failure recorded beside this item. |
| 23 | `grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39` | `A029` | `retrieval-chunk-miss` | `docs/concepts/policies` at rank 2 supplies the 'root policy cannot be modified' half, but `docs/concepts/tokens` at rank 4 does not carry 'Root tokens are tokens that have the `root` policy attached'; the answer is nonetheless correct, a chunk-placement miss with no visible answer error. |
| 24 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | `A015` | `retrieval-chunk-miss` | `tune-server-performance` at rank 7 without the 131072 row, and this time the generator answered the opposite -- 'unlimited in size... no fixed default entry count' -- the wrong-answer form of the same chunk boundary. |
| 25 | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | `A018` | `context-budget-drop` | the quote-bearing `docs/auth/login-mfa` chunk is at rank 10 and the window holds 8, so 'Vault allows for 5 consecutive failed TOTP passcode validations' never entered the prompt; the abstention is the window's doing, not the generator's. |
| 26 | `grid-fixed-dense-late_chunking-20261030T161040-76813f02` | `A004` | `context-budget-drop` | `docs/concepts/mount-migration` is at rank 9, outside the eight-chunk window; the answer is right anyway ('the status can be in-progress'), so a real window drop is hidden behind a lucky answer. |
| 27 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | `A021` | `context-budget-drop` | the lease-count row of `docs/concepts/resource-quotas` sits at rank 9; the answer is correct ('lease count quota... enterprise-only'), again hiding the drop. |
| 28 | `grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39` | `A005` | `context-budget-drop` | the prefix sentence is at rank 9, so the prompt held the service-versus-batch differences but not 'tokens have a specific prefix'; the generator abstained and listed the differences it could see, which is what a window drop looks like from outside. |
| 29 | `grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222` | `A033` | `context-budget-drop` | the audit-page quote is at rank 1 and 'Vault will not respond to requests when audit devices are not enabled' is at rank 10, outside the window; the answer still contains both halves, so the second half did not come from the retrieved context. |
| 30 | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | `A040` | `citation-quote-not-in-chunk` | the 300-character quote is verbatim for 74 characters and then diverges where the chunk writes a markdown link (`[TLS](...)`) that the model flattened to plain 'TLS': the prose is faithful and the exact-string containment check is not. |
| 31 | `grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950` | `A023` | `citation-quote-not-in-chunk` | verbatim for 54 characters, then the model inserts '(e.g., 1.16, 1.19)' which the page does not contain, and resumes verbatim afterwards: an inserted example inside an otherwise real span. |
| 32 | `grid-fixed-hybrid-late_chunking-20261030T161751-66c05c39` | `A027` | `citation-quote-not-in-chunk` | the opening 40 characters of the Shamir quote occur nowhere in the cited `docs/commands/operator/init` chunk, and the full quote occurs in no rebuilt chunk: a summary of the page returned as a quotation. |
| 33 | `grid-fixed-hybrid-plain-20261030T125429-6170ae66` | `A032` | `citation-quote-not-in-chunk` | the cited `docs/concepts/client-count` chunk defines what a client is; the 'entity aliases...' sentence is in `docs/concepts/identity`, retrieved at rank 1, so the passage was in the prompt and the citation names the wrong page. |
| 34 | `grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222` | `A004` | `citation-quote-not-in-chunk` | the quoted sentence exists verbatim in `docs/concepts/mount-migration` chunk `c-3e3cd28f822244e7`, retrieved at rank 1, and is cited against `api-docs/system/remount`, where it does not occur: real evidence, wrong citation target. |
| 35 | `grid-fixed-rerank-late_chunking-20261030T163138-8f5d6ac0` | `A038` | `citation-quote-not-in-chunk` | verbatim for 155 of 183 characters and then diverges at the chunk's markdown link `[generate-root](...)`, which the model wrote as plain `generate-root`; the sentence is faithful and the containment check is formatting-sensitive. |
| 36 | `grid-fixed-rerank-contextual_prefix-20261030T145745-14c0b222` | `A040` | `citation-chunk-not-retrieved` | the model cited `c-87c83bb5d923ceb`; the real chunk is `c-87c83bb5d923cece`, one hex character longer, and it was retrieved at rank 2 -- the id was mistyped, so an otherwise correct citation was rejected as pointing outside the context. |
| 37 | `grid-fixed-rerank-plain-20261030T125648-57be667d` | `A040` | `citation-chunk-not-retrieved` | same mistyped id in the plain cell (`c-87c83bb5d923ceb` against `c-87c83bb5d923cece` at rank 2): the defect is chunk-id fidelity in the generator's output, not retrieval. |
| 38 | `grid-fixed-dense-contextual_prefix-20261030T142519-d947855e` | `A027` | `generation-parse-failure` | `tokens_out` is 3200 against `max_tokens` 1600 and the response body is empty: the call consumed its whole output budget and emitted no envelope, with both evidence quotes in the window at ranks 2 and 1. |
| 39 | `grid-fixed-dense-plain-20261030T124637-8ae4eb06` | `A031` | `generation-parse-failure` | the envelope is cut mid-quote after 382 characters with `tokens_out` 3200 = 2 x `max_tokens`; the item also lost its second evidence passage to the window (rank 10 of 8), so two defects stack and the empty body is counted here. |
| 40 | `grid-fixed-hybrid-contextual_prefix-20261030T144111-0d58c950` | `A027` | `generation-parse-failure` | the provider returned an empty string with `tokens_out` at the 3200 cap and no error detail: budget exhaustion with nothing written, a different mechanism from a truncated envelope and the same class. |


## Counts per class per cell

Row labels are the class names; the columns are the cells of `reports/matrix.md`, whose table pairs
each cell with its run id.

| class | `cell-fixed-dense-contextual_prefix` | `cell-fixed-dense-late_chunking` | `cell-fixed-dense-plain` | `cell-fixed-hybrid-contextual_prefix` | `cell-fixed-hybrid-late_chunking` | `cell-fixed-hybrid-plain` | `cell-fixed-rerank-contextual_prefix` | `cell-fixed-rerank-late_chunking` | `cell-fixed-rerank-plain` | `cell-recursive_parent_child-dense-contextual_prefix` | `cell-recursive_parent_child-dense-late_chunking` | `cell-recursive_parent_child-dense-plain` | `cell-recursive_parent_child-hybrid-contextual_prefix` | `cell-recursive_parent_child-hybrid-late_chunking` | `cell-recursive_parent_child-hybrid-plain` | `cell-recursive_parent_child-rerank-contextual_prefix` | `cell-recursive_parent_child-rerank-late_chunking` | `cell-recursive_parent_child-rerank-plain` | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `retrieval-document-miss` | 8 | 24 | 9 | 5 | 9 | 6 | 5 | 9 | 6 | 7 | 25 | 8 | 5 | 8 | 5 | 5 | 8 | 5 | 157 |
| `retrieval-chunk-miss` | 5 | 5 | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 3 | 4 | 4 | 1 | 1 | 1 | 1 | 1 | 1 | 39 |
| `context-budget-drop` | 2 | 1 | 4 | 0 | 1 | 0 | 1 | 1 | 1 | 3 | 1 | 2 | 1 | 0 | 0 | 5 | 2 | 4 | 29 |
| `generator-over-abstention` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `generator-under-abstention` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `citation-quote-not-in-chunk` | 1 | 0 | 0 | 1 | 1 | 1 | 1 | 1 | 2 | 0 | 0 | 3 | 2 | 4 | 3 | 3 | 3 | 0 | 26 |
| `citation-span-out-of-bounds` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `citation-chunk-not-retrieved` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 |
| `generation-parse-failure` | 1 | 0 | 1 | 2 | 1 | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | 2 | 3 | 17 |
| **total** | **17** | **30** | **16** | **10** | **14** | **8** | **12** | **14** | **15** | **13** | **31** | **18** | **9** | **13** | **9** | **17** | **16** | **13** | **275** |


## Classes that never fire

Three, and that is a result rather than a gap in the extraction:

- **`generator-under-abstention` never fires.** Abstention recall on the twenty unanswerable items is
  1.0000 in every one of the eighteen cells: the generator declined every negative. Whatever is wrong
  with this system, it is not answering questions the knowledge base cannot answer.
- **`citation-span-out-of-bounds` never fires.** The span is derived by string search rather than
  asked of the model, so a quote either locates or it does not; there is no path that produces a span
  which does not delimit its own quote. The class is structurally unreachable while spans are derived
  rather than returned, and it deserves removing or re-arguing rather than being carried forever.
- **`generator-over-abstention` never fires either**, and the reason is worth stating precisely: the
  64 abstentions on answerable items across the matrix are exactly accounted for by the 64 items
  whose evidence was lost first (43 document misses, 13 chunk misses, 8 window drops). Not one
  abstention had its whole evidence set inside the window. The class earns its place because that
  accounting is what proves the generator is not the component refusing answers; if a later run
  changes the window or the index, this class is how the change would surface.

## What this says about where the system fails

**It fails before generation.** 196 of the 275 events (71%) are evidence that never reached the
prompt, and every abstention on an answerable question is explained by one of them. The generator's
own defects are the small end of the table: 26 mangled quotes and 17 unparsable responses on a base
of 1,080 item-cells.

**The failure is coverage, not ordering.** The same pages fail under every ranker and every chunk
strategy: `A028` misses `docs/configuration/seal/seal-best-practices` in all 18 cells, `A034` and
`A035` their own pages in all 18, `A030` in 17. Twenty-five distinct items carry the 157 document
misses, and the ranking experiments barely move them -- hybrid and rerank lift hit@10 to 0.88 while
the same conceptual pages stay absent. That is a corpus and question-vocabulary problem (the golden
questions ask about mechanisms the pages phrase differently), not a scoring problem, and no amount of
reranking will fix it.

**Two retrieval families with different fixes.** Page-level absence (157) is an index-recall problem:
the passage was never a candidate. Chunk-boundary loss (39, from 12 items -- `A015` alone accounts
for 10) is a *chunking* problem: the page is returned and the sentence is in the neighbouring chunk.
The second family is the one the chunking experiments could have fixed and did not, because `fixed`
and `recursive_parent_child` split tables the same way.

**The window costs more than it should.** With `retrieval.k = 10` and `llm.context_chunks = 8`, 29
quote-bearing chunks were retrieved and then dropped before the prompt. Twenty-one of those items
still answered correctly, which is why the per-cell over-abstention rate (0.025 to 0.40 in
`reports/matrix.md`) reads like a generator property when it is mostly a window property. Either
widen the window to k or set k to the window; carrying two numbers that disagree buys nothing.

**The metric hides a third of this.** hit@10 averages 0.81 across the matrix, but 56 of the 196
evidence-loss events are items that metric counted as hits, because it stops at the first gold quote
it finds. A multi-hop item with one leg retrieved scores a hit and answers half the question. On this
evidence hit@10 is not a recall estimate; recall over *all* gold quotes would be, and it is 0.73 over
the same cells (196 lost of 720 answerable item-cells, 27%).

**Quotes fail for four different reasons, and not all are the model's fault.** The 26
`citation-quote-not-in-chunk` events decompose as: 8 where the quote is faithful and the model
flattened a markdown link (`[TLS](...)` written as `TLS`), so exact-string containment rejected it; 6
that diverge into text the chunk does not contain (an inserted example, a spliced clause); 9 whose
text occurs in no rebuilt chunk at all (a summary returned as a quotation); and 3 where the quote is
real, verbatim, and in a *different* retrieved chunk, so the citation points at the wrong page. The
first group is a verifier bug -- normalise markdown links before containment and 8 of the 26 disappear
without touching the generator.

**Parse failures are three questions, not a diffuse tax.** 17 events over just three items (`A031`
x8, `A027` x7, `A029` x2), every one at `tokens_out = 3200` against `max_tokens = 1600`: the answers
that need a two-passage join are the ones that run out of output budget and return an empty or
truncated envelope. Raising the cap for multi-hop items would clear most of this class. Eleven of the
17 sit on items that had already lost evidence, so it is second-order, not first.

**What this taxonomy cannot see**, and what the report should not imply otherwise: the cells ran with
`judge_enabled = false`, so an answer that is wrong while every citation checks out is invisible
here. Several sampled rows show the mirror image: rows 14, 17, 23, 26, 27 and 29 are evidence-loss
events and row 33 a mis-citation, and all seven answers are substantively correct -- produced without
a retrieved passage that supports them. The counts are therefore **lost-evidence and malformed-output events, an upper bound on
answer errors, not a wrong-answer count**; a wrong-answer taxonomy needs the judge cells or the
`correctness` metric switched on, and that is the next thing this note would need.

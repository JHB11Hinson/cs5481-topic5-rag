# Golden QA set audit (agent-performed, authorised, re-checkable)

Fourteen items of `golden/v1.jsonl`, read one by one against the corpus: ten stratified across the strata (six answerable, four near-miss), plus the four that a question/quote overlap screen over all forty answerable items flagged hardest.
Provenance: **the implementing agent performed this audit at the group's authorisation.**
It is not an independent human review, and nothing here should be described as one.
Every row can be re-checked: the quote is printed verbatim, its `doc_id` names the
document, and the three signals are computed by `scripts/golden_audit.py`, which prints
the same packet to the terminal.

## What is already proven by program, and what is not

`ragqa golden validate` proves each quote occurs **verbatim** in its document and is
**unique** in the corpus. It cannot prove the question is worth asking. The four
criteria below are the part that needs a reader.

1. **Anchored** — the evidence quote actually contains what the question asks about.
2. **Unambiguous** — one reasonable reading; no second item would answer it better.
3. **Not common knowledge** — a reader could not answer it from general Vault experience.
4. **Answer within evidence** — `reference_answer` says no more than the quote supports.

## The fourteen

| # | id | stratum | question | verdict | note |
|---|---|---|---|---|---|
| 1 | A001 | fact_lookup | What state does a Vault server start in when it is launched? | pass (weak) | Criterion 3 only: *Vault starts sealed* is the first fact in almost every Vault tutorial, so a reader with product experience answers it without the document. Kept because an anchor item that a stumbler cannot miss is useful for detecting a broken pipeline; do not count it as evidence of retrieval quality. |
| 2 | A008 | fact_lookup | What does the vault.core.leadership_lost metric measure? | pass | Question names the metric; quote defines it; the reference answer restates the quote and adds nothing (0.818 answer-token overlap, similarity 0.67). |
| 3 | A015 | param_value | How many entries does Vault's storage read cache hold by default? | pass (caveat) | The quote is `The value is the number of entries and the default value is **131072**.` — it never names the cache. It is the storage read cache: the preceding sentence reads *Vault uses a Least Recently Used (LRU) read cache for the physical storage subsystem with a tunable value, `cache_size`*, under `### Cache size`. So the **doc_id plus section** carry the anchor while the quote alone does not; a claim quoting this sentence is containable but not self-locating. v2 should extend the quote to the LRU sentence. |
| 4 | A022 | table_content | Which quota type limits requests per second, and does the Community edition support it? | pass (caveat) | The quote is one table row, `\| Rate limit quotas \| Limit maximum amount of requests per second (RPS) … \| ✅ \| ✅ \|`. The two check marks are meaningless without the header row naming the editions, and the reference answer (`both editions support them`) does not stand on the quoted row. The table is the *point* of this stratum — a naive chunker loses the header, and this item detects exactly that — so the item is worth keeping, but the recorded evidence under-supports its own answer. v2 should include the header row. |
| 5 | A030 | multi_hop | If you remount a secrets engine that hands out dynamic credentials, what happens to credentials already issued, and why? | pass | Two documents, two quotes, and the inference between them is the stratum's purpose: remount revokes leases, every dynamic secret carries a lease, therefore issued credentials go. The reference answer states the inference explicitly, which is what a graded answer should contain. |
| 6 | A035 | concept | Why does Vault encrypt its data encryption key with a second key instead of keeping it in plaintext? | pass | Quote is the mechanism, answer is its purpose, no fact beyond the quote (0.5 overlap). |
| 7 | A005 | fact_lookup | How can you tell from the value of a token whether it is a batch token or a service token? | pass (weak) | Quote says tokens carry a prefix that indicates their type; the question asks specifically batch versus service, and neither the quote nor the reference answer names the two prefixes. Answerable from the page, but the item's specificity is lower than its stratum suggests. |
| 8 | A006 | fact_lookup | While a node runs in recovery mode, how many recovery tokens can exist at a time? | pass | `Only a single recovery token can be generated.` against `Exactly one.` — the reference answer shares **zero** tokens with its quote, and that is a tokenisation artefact, not a defect. This is the counter-example that shows why the overlap signal is a screen and not a verdict. |
| 9 | A028 | multi_hop | With auto unseal, what comes back at initialisation instead of unseal keys, and what still needs that credential later? | pass (caveat) | First quote is self-contained (recovery keys replace unseal keys at initialisation). The second, `These are still required for highly privileged actions, such as generating new root keys.`, starts with a pronoun whose antecedent sits in the previous sentence of that document. A claim citing it is containable but its support depends on text the verifier never sees. v2 should extend that quote by one sentence. |
| 10 | A038 | concept | Why does Vault keep separate keys for separate jobs instead of one key for everything? | **defect (mild)** | The reference answer says more than its evidence: *stores different encryption keys for different purposes, **and rotation then targets the key that needs changing***. The quoted sentence supports only the first clause (answer-token overlap 0.353). The answer is true of the page, so the item is not unanswerable — but a correct answer that mentions rotation cannot be supported by the quote as recorded. v2 must either extend the quote or drop the second clause. |
| 11 | U003 | near_miss | In Vault 1.22, what is the default value of the listener option disable_gzip? | pass | Checked by search rather than by reading: `disable_gzip` occurs in **0 of 1,268** documents, so asking for its 1.22 default is genuinely unanswerable, and the nearest document exists and shares vocabulary with the question. |
| 12 | U008 | near_miss | What is the current size of the raft log on each of my Vault nodes? | pass | Asks for the current raft log size on *my* nodes — runtime state of a specific cluster. The nearest page describes snapshot thresholds, so the topically-adjacent-but-unanswerable condition holds. |
| 13 | U014 | near_miss | How do I move a live Integrated Storage cluster onto Consul storage without downtime? | pass | Asks how to move **off** Integrated Storage; the corpus documents only the reverse migration (Consul → Integrated Storage). Direction-specific absence is the cleanest kind of near-miss here. |
| 14 | U019 | near_miss | How many client seats does the HCP Vault Dedicated Essentials tier include? | pass | Asks for a commercial tier's seat allowance; the corpus discusses client counting and names no HCP tier. Commercial packaging, adjacent page present. |

## Evidence and signals per item

### A001 — fact_lookup, difficulty easy

- question: What state does a Vault server start in when it is launched?
- reference answer: It starts in a sealed state.
- evidence `docs/concepts/seal`: When you start a Vault server, it starts in a sealed state.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 1.0, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.667, "quote_chars": 59}`

### A008 — fact_lookup, difficulty medium

- question: What does the vault.core.leadership_lost metric measure?
- reference answer: How long a server held the leader position before losing it.
- evidence `docs/internals/telemetry/key-metrics`: The metric `vault.core.leadership_lost` measures the duration a server held the leader position before losing it.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.818, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.625, "quote_chars": 113}`

### A015 — param_value, difficulty medium

- question: How many entries does Vault's storage read cache hold by default?
- reference answer: 131072 entries.
- evidence `docs/concepts/tune-server-performance`: The value is the number of entries and the default value is **131072**.
- signals: `{"answer_identifiers": ["131072"], "answer_token_overlap_with_quote": 1.0, "identifier_coverage": 1.0, "identifiers_in_quote": ["131072"], "question_token_overlap_with_quote": 0.167, "quote_chars": 71}`

### A022 — table_content, difficulty medium

- question: Which quota type limits requests per second, and does the Community edition support it?
- reference answer: Rate limit quotas; yes, both editions support them.
- evidence `docs/concepts/resource-quotas`: | Rate limit quotas | Limit maximum amount of requests per second (RPS) to a system or mount to protect network bandwidth | &#9989; | &#9989; |
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.375, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.214, "quote_chars": 143}`

### A030 — multi_hop, difficulty hard

- question: If you remount a secrets engine that hands out dynamic credentials, what happens to credentials already issued, and why?
- reference answer: Remounting revokes the existing leases on that mount, and every dynamic secret carries a lease, so the issued credentials go with them.
- evidence `docs/concepts/mount-migration`: The remount operation will result in existing leases on a mount being revoked.
- evidence `docs/concepts/lease`: All dynamic secrets in Vault are required to have a lease.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.286, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.111, "quote_chars": 78}`

### A035 — concept, difficulty medium

- question: Why does Vault encrypt its data encryption key with a second key instead of keeping it in plaintext?
- reference answer: So the encryption key stored with the data is itself protected by the root key.
- evidence `docs/concepts/seal`: To protect this encryption key, Vault encrypts it using another encryption key known as the root key and stores it with the data.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.5, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.353, "quote_chars": 129}`

### A005 — fact_lookup, difficulty medium

- question: How can you tell from the value of a token whether it is a batch token or a service token?
- reference answer: From its prefix, which indicates the token type.
- evidence `docs/concepts/tokens`: Tokens have a specific prefix that indicates their type.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.375, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.062, "quote_chars": 56}`

### A006 — fact_lookup, difficulty easy

- question: While a node runs in recovery mode, how many recovery tokens can exist at a time?
- reference answer: Exactly one.
- evidence `docs/concepts/recovery-mode`: Only a single recovery token can be generated.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.0, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.214, "quote_chars": 46}`

### A028 — multi_hop, difficulty hard

- question: With auto unseal, what comes back at initialisation instead of unseal keys, and what still needs that credential later?
- reference answer: Recovery keys, and they are still required for highly privileged actions such as generating new root keys.
- evidence `docs/concepts/seal`: When you initialize Vault using an HSM or KMS, Vault returns recovery keys to the operator rather than unseal keys.
- evidence `docs/configuration/seal/seal-best-practices`: These are still required for highly privileged actions, such as generating new root keys.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.125, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.118, "quote_chars": 115}`

### A038 — concept, difficulty medium

- question: Why does Vault keep separate keys for separate jobs instead of one key for everything?
- reference answer: Because it stores different encryption keys for different purposes, and rotation then targets the key that needs changing.
- evidence `docs/internals/rotation`: Vault stores different encryption keys for different purposes.
- signals: `{"answer_identifiers": [], "answer_token_overlap_with_quote": 0.353, "identifier_coverage": null, "identifiers_in_quote": [], "question_token_overlap_with_quote": 0.231, "quote_chars": 62}`

### U003 — near_miss, difficulty medium

- question: In Vault 1.22, what is the default value of the listener option disable_gzip?
- why unanswerable: The snapshot documents 1.21.x; disable_gzip is not documented in it at all.
- nearest document: `docs/configuration/listener/tcp`
- signals: `{"near_doc_exists": true, "near_doc_mentions_key_terms": true, "why_unanswerable_words": 12}`

### U008 — near_miss, difficulty medium

- question: What is the current size of the raft log on each of my Vault nodes?
- why unanswerable: Runtime state of a specific cluster; the raft configuration pages describe snapshot thresholds, not the size of anyone's log.
- nearest document: `docs/configuration/storage/raft`
- signals: `{"near_doc_exists": true, "near_doc_mentions_key_terms": true, "why_unanswerable_words": 19}`

### U014 — near_miss, difficulty hard

- question: How do I move a live Integrated Storage cluster onto Consul storage without downtime?
- why unanswerable: Only the reverse migration, Consul storage to Integrated Storage, has a procedure page; moving off Integrated Storage is never described.
- nearest document: `docs/concepts/integrated-storage/migrate-consul-storage`
- signals: `{"near_doc_exists": true, "near_doc_mentions_key_terms": true, "why_unanswerable_words": 20}`

### U019 — near_miss, difficulty medium

- question: How many client seats does the HCP Vault Dedicated Essentials tier include?
- why unanswerable: Commercial packaging: the corpus discusses client counting but names no HCP tier or seat allowance.
- nearest document: `docs/concepts/client-count`
- signals: `{"near_doc_exists": true, "near_doc_mentions_key_terms": true, "why_unanswerable_words": 15}`

## Screen over all forty answerable items

The three caveats above share one measurable property: the question's content words barely
appear in its own evidence. Screening all forty answerable items by that overlap (question
tokens present in the quote) flags six below 0.25, and all four that were then read are
above; the other two are `A015` and `A022`, already read:

| id | stratum | question overlap | answer overlap | read | verdict |
|---|---|---|---|---|---|
| A005 | fact_lookup | 0.062 | 0.375 | yes | pass (weak) |
| A006 | fact_lookup | 0.214 | **0.000** | yes | pass — artefact |
| A015 | param_value | 0.167 | 1.000 | yes | pass (caveat) |
| A022 | table_content | 0.214 | 0.375 | yes | pass (caveat) |
| A028 | multi_hop | 0.176 | 0.875 | yes | pass (caveat) |
| A038 | concept | 0.231 | 0.353 | yes | **defect (mild)** |

So the screen found a real defect (A038) and three quote-extension candidates, and it also
produced one false alarm (A006, zero overlap for a semantically exact answer). Use it to
choose what to read; never use it to decide.

## Findings and what they imply

## Findings and what they imply

Fourteen items were read (ten stratified, plus the four the screen flagged hardest). **One
defect and three under-specified quotes, thirteen passes.**

1. **One real defect, `A038`**: the reference answer asserts a rotation consequence that its
   quoted sentence does not contain. The answer is true of the page, so no number in the
   report is wrong; what is wrong is that a correct answer mentioning rotation cannot be
   supported by the recorded evidence.
2. **Three quotes are containable but not self-locating** (`A015`, `A022`, `A028`): a pronoun
   whose antecedent is outside the quote, a table row without its header, a sentence about
   "the value" that never names the setting. This is a property of sentence-level quotes in
   reference documentation, not sloppiness, and it is worth stating in the report because it
   is exactly what the containment check cannot see: **containment proves the quote is real,
   not that the quote is sufficient**.
3. **One item is answerable from general knowledge** (`A001`). Kept deliberately as an anchor.
4. **The overlap signal is a screen, not a verdict** (`A006`).

### Proposed `golden/v2.jsonl` edits (v1 is immutable)

| id | change | cost if not made |
|---|---|---|
| A038 | extend the evidence quote to the rotation sentence, or drop *and rotation then targets the key that needs changing* from the reference answer | the item systematically counts a correct answer as unsupported |
| A015 | extend the quote one sentence, to include *Vault uses a Least Recently Used (LRU) read cache for the physical storage subsystem with a tunable value, `cache_size`* | the quote alone does not say which setting it describes |
| A022 | include the table's header row in the quote | the recorded evidence cannot support "both editions" |
| A028 | extend the second quote by one sentence so its pronoun has an antecedent | same, for the recovery-key half |

None of the four changes the corpus, the strata quotas, or any metric that has already been
reported: they change what the *evidence field* contains, which is what a re-chunk and a
re-verification read. Adopting them means regenerating `golden/v2.jsonl`, re-running the
eighteen cells and the four baselines, and re-deriving every table — which is why they are
recorded here rather than applied at the end of the build.

### What this audit is, and is not

It is the implementing agent reading fourteen items against the corpus, at the group's
authorisation, with every quote printed verbatim and every signal reproducible by
`python scripts/golden_audit.py --ids …`. It is **not** an independent human review, and
the report says so: `verified_by` stays `automated:corpus-anchored` on all sixty items. What
changed is that the project now knows the size of the gap: **one defect in fourteen read**,
and a screen that can point a human at the remaining twenty-six answerable items in a
minute.


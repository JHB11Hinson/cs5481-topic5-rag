# How far can a support judge be trusted?

Ticket 10. Two judges rule on whether a citation supports its claim: a local NLI
cross-encoder and `deepseek-v4-pro`. Neither is ground truth, so both are measured
against 30 claims labelled by hand, and the report is only allowed to lean on a
layer that clears a bar fixed in advance.

**The bar, fixed before any judge was run:** Cohen's kappa ≥ 0.60 against the hand
labels. It is stored in `notes/judge-calibration.json` (`"bar": 0.6`) next to the
labels themselves, so the claim that it was set in advance is checkable rather than
asserted. Raw agreement alone would not do: most citations in this system are
supported, so a layer that says "supported" to everything scores well on raw
agreement while telling us nothing.

## Method

**Where the claims come from.** `deepseek-v4.1-flash` produced 50 claim rows across
the three real-generation runs in `runs/` (12 / 17 / 21). Containment — the string
check from ADR-0004 — rejected 3 of them (`quote_not_in_chunk`), so 47 reached a
position where a judge would be asked, carrying 34 distinct claim texts. The headline
run `real-llm-20261030T113604-a5c0a3e4` has only 21 claims, 19 of which survive
containment, so sixteen of the 20 verbatim rows come from it (the other three of its
19 repeat claims already in the set) and four come from
`real-llm-20261030T113427-6dba1b8f`, which has the same corpus snapshot, chunking and
chunk ids and adds claim shapes the headline run did not produce (the dev-server
address default, the unseal-key direction of encryption, the barrier argument).

**Twenty rows are verbatim claims from those runs**, chosen deliberately rather than
sampled: the table rows, the code fence, the two claims that talk about what a
document says instead of about Vault, the chain-compression claim, and the
default-value claims are all in, because those are the shapes a judge is likely to
get wrong.

**Ten rows are controlled negatives.** This is the honest part of the set and it
needs stating plainly: **none of the 47 containment-passing claims is false.** The
generator's real errors in these runs were citations that pointed nowhere, and those
are caught by containment before any judge sees them. A 30-row set with a constant
human label cannot estimate kappa at all — with one rater constant, chance agreement
is 1 and kappa is undefined — and it cannot measure a judge's false positives, which
is exactly the failure mode a permissive judge has. So ten negatives were built by
applying one documented edit to a verbatim claim: a value flipped, a negation
dropped, a relation reversed, a default borrowed from the neighbouring option, a
path swapped for the one another page uses. The quote and the chunk stay the ones the
generator cited, which is what makes them drift cases — the quote is real, the
assertion is not — and each row records `origin: "perturbed"`, the claim it was
derived from (`derived_from`) and the edit (`edit`). The 20 / 10 split is 2:1.

**The labels are hand labels.** Every row was read against the full cited chunk, not
against the quote, and carries a one-line justification in the JSON and in the table
below. The calibration script reads that file and never writes a label.

**How a row is judged.** Through the production path:
`verify.check_claims` for containment, then `SupportJudges.judge_claim`, which sends
the whole chunk as the NLI premise and asks the hosted model the same question in
words. Both verdicts are cached in `notes/judge-calibration.verdicts.json`, so
re-running the script costs nothing and prints the same numbers.

**Two judge settings were chosen deliberately.**

- *NLI threshold 0.5*, from `configs/real_llm.yaml` (`judge.nli_threshold`), i.e. the
  value the pipeline runs with, not a value tuned on this set.
- *Hosted judge with its thinking channel on, `max_tokens` 700.* `deepseek-v4-pro`
  reasons before answering, and a 200-token budget can be consumed by reasoning
  alone, returning empty content that the parser would score as "unsupported" —
  a silent bias toward false. With 700 the calibration calls spent 4,924 output
  tokens over 30 calls (≈164 each, of which roughly 50–80 were reasoning). The
  cheap alternative, `reasoning_effort: "none"`, was probed separately on one claim:
  24 completion tokens instead of 74–82, gateway list cost $0.0002 instead of
  $0.00037, same verdict. It is the right setting for the 18-cell matrix; it is not
  the right setting for the reference layer this calibration is measuring, because
  the point of the hosted layer is that it deliberates on drift. `judges.make()`
  therefore leaves the thinking channel on: wiring the cheap setting into a run needs
  a `judge.reasoning_effort` config key, and `ragqa/config.py` belongs to another
  ticket, so the flag exists in code (`LLMJudge(..., reasoning_effort="none")`) while
  every judge-enabled run pays the deliberating price until that key is added.

**Reproduce.**

```bash
python scripts/calibrate_judges.py            # both layers, cached, ~30 calls on a cold cache
python scripts/calibrate_judges.py --no-llm   # NLI only, offline
```

## A correction this calibration forced

The first NLI run scored kappa −0.33 with recall 0.05: it called "A Vault server
starts in a sealed state" unsupported against the sentence saying exactly that.
`ragqa/judges.py` was reading the cross-encoder's probabilities as
`[contradiction, neutral, entailment]`, the original MNLI convention;
`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` is labelled
`[entailment, neutral, contradiction]`, so index 2 — contradiction — was being read
as entailment and every verdict was inverted. The layer now reads `id2label` from the
checkpoint (`NLIJudge._label_order`) and keeps the MNLI order only as a fallback;
`tests/test_judge_calibration.py` pins both orders against the same logits. Any NLI
number produced before this fix means the opposite of what it says.

<!-- BEGIN GENERATED: judge calibration tables -->

## The 30 labelled claims and what each layer said

`yes` = supported, `no` = unsupported, `-` = layer was not asked (containment failed).

| # | claim id | claim | human | NLI | judge | one-line justification |
|---|---|---|---|---|---|---|
| 1 | `C-A001-c1` | A Vault server starts in a sealed state. | yes | yes | yes | The chunk's first sentence says exactly this: a Vault server starts in a sealed state. |
| 2 | `C-A001-c2` | In the sealed state, Vault can access physical storage but cannot decrypt any of the data on it. | yes | yes | yes | Verbatim entailment from sentence two: in the sealed state Vault reaches physical storage but cannot decrypt its data. |
| 3 | `C-A001-c3` | Until it is unsealed, a Vault server cannot respond to requests. | yes | yes | yes | The chunk says a server must be unsealed before it can respond to requests; the claim is the same fact stated negatively, and the entailment holds. |
| 4 | `C-A002-c1` | The setup documentation states that on a dev-mode server the v2 kv secrets engine is enabled by default at the path demo/ (whereas non-dev servers currently default to v1). | yes | yes | yes | The chunk states the dev-mode default is v2 at demo/ and that non-dev servers currently default to v1; the claim only attributes that statement to the page it is on. |
| 5 | `C-A002-c2` | The dev-server concepts page, by contrast, states that a v2 KV secret engine is mounted at secret/ on a dev server. | yes | yes | yes | Under the dev-server page's Properties list: 'A v2 KV secret engine is mounted at secret/'. The claim reports the page's statement accurately. |
| 6 | `C-A003-c1` | During initialization, Vault generates a root key that is stored encrypted in the storage backend. | yes | yes | yes | Chunk: the root key is generated at init, stored in the storage backend, and 'the root key itself is encrypted'. 'Stored encrypted' is the same fact. |
| 7 | `C-A003-c2` | The root key is encrypted and requires an unseal key to decrypt it. | yes | yes | yes | Chunk: 'The root key itself is encrypted and requires an unseal key to decrypt it.' Same assertion, trimmed. |
| 8 | `C-A005-c1` | The default value of the reload option in the cert auto-auth method is false. | yes | yes | yes | Chunk documents the option as '(bool: optional, default: false)'; the claim reads that default out directly. |
| 9 | `C-A006-c1` | A local mount can be created on a performance primary, and it is not visible to its performance secondaries. | yes | yes | yes | Chunk: 'A local mount created on a performance primary isn't visible at all to its performance secondaries.' |
| 10 | `C-A006-c3` | Local mounts replicate their data only to disaster recovery secondaries. | yes | no | no | That sentence is in the cited chunk verbatim, and the storage-class list agrees: 'local: only downstream disaster recovery clusters receive it'. |
| 11 | `C-A007-c1` | The root key is an AES key encrypted by the seal mechanism, and it encrypts the key ring. | yes | yes | yes | The table row for Root Key reads 'AES key that is encrypted by the seal mechanism. This encrypts the key ring.' The claim restates the row without drift. |
| 12 | `C-A008-c1` | The telemetry metrics table reports non-entity counts as a gauge metric, and the value counts the number of distinct non entities across all namespaces that created a token during the configured reporting period. | yes | yes | yes | The metric row is 'gauge \| non entities \| The number of distinct non entities (across all namespaces) that created a token during the configured reporting period.' |
| 13 | `C-A009-c3` | The shards from init are what operators later supply to unseal: shares are added one at a time until enough exist to reconstruct the key, which then decrypts the root key. | yes | yes | no | Chunk: operators add shares 'until Vault has enough shares to reconstruct the key. Then, Vault uses the unseal key to decrypt the root key.' The claim compresses the intermediate unseal key into 'the key' but does not change the chain. |
| 14 | `C-A010-c1` | Vault encrypts the encryption key with another key, the root key, to protect it rather than leaving it in plaintext. | yes | yes | yes | Chunk: 'To protect this encryption key, Vault encrypts it using another encryption key known as the root key.' The 'not plaintext' clause is implied by the encryption itself. |
| 15 | `C-A010-c2` | This creates a chain where the root key is needed to decrypt the encryption key, and the root key itself is encrypted using the unseal key. | yes | yes | yes | The same chunk states both links of the chain: the root key decrypts the encryption key, and the root key is encrypted with the unseal key. |
| 16 | `C-U005-c1` | The Terraform resource name shown for the Vault AWS auth role is `vault_aws_auth_backend_role`. | yes | yes | yes | The cited code fence is 'resource "vault_aws_auth_backend_role" "aws_irsa_role"', so the resource type named in the claim is the one shown. (The golden item is a near-miss, but this claim about the chunk is still supported.) |
| 17 | `B-A002-c1` | When running a dev-mode server, the v2 kv secrets engine is enabled by default at the path demo/. | yes | yes | yes | Verbatim: 'when running a dev-mode server, the v2 kv secrets engine is enabled by default at the path demo/'. |
| 18 | `B-A003-c3` | Vault encrypts the root key using the unseal key and stores it alongside all other Vault data. | yes | yes | yes | Verbatim: 'Vault encrypts the root key using the unseal key, and stores it alongside all other Vault data.' |
| 19 | `B-A004-c1` | The Vault dev server listens by default on 127.0.0.1:8200 without TLS. | yes | yes | yes | The Properties bullet 'Bound to local address without TLS' gives 127.0.0.1:8200 as the default server address, without TLS. |
| 20 | `B-A010-c2` | Vault treats the storage backend as untrusted because it resides outside the barrier, so Vault encrypts data before sending it to storage; this prevents compromise if an attacker gains access to the storage backend. | yes | yes | yes | The barrier section says the storage backend sits outside the barrier and is therefore untrusted, so Vault encrypts data before writing it; the claim repeats that in one sentence. |
| 21 | `P01` | The default value of the `reload` option in the cert auto-auth method is `true`. | no | no | no | The chunk documents default: false. A true default is the opposite of the cited text. |
| 22 | `P02` | The `reload` option in the cert auto-auth method defaults to `1m`. | no | yes | no | `1m` is reload_period's default; reload's own default is false, so the value is borrowed from the wrong option. |
| 23 | `P03` | The Vault dev server listens by default on `0.0.0.0:8200` without TLS. | no | no | no | The chunk names 127.0.0.1 as the default server address; the wildcard address is a different, unreachable claim. |
| 24 | `P04` | When running a dev-mode server, the v2 kv secrets engine is enabled by default at the path `secret/`. | no | no | no | Against this chunk the path is demo/; secret/ is only correct on a different page, so the citation does not support the claim. |
| 25 | `P05` | In the sealed state, Vault cannot access the physical storage, but it can decrypt the data on it. | no | no | no | The chunk states the opposite in both halves: physical storage is reachable, decryption is not. |
| 26 | `P06` | Vault encrypts the unseal key using the root key and stores it alongside all other Vault data. | no | yes | no | The direction in the chunk is root key encrypted by the unseal key; the claim reverses the key hierarchy. |
| 27 | `P07` | A local mount created on a performance primary is visible to its performance secondaries. | no | no | no | The chunk says such a mount 'isn't visible at all' to performance secondaries. Dropping the negation inverts it. |
| 28 | `P08` | The root key is an AES key that encrypts the seal mechanism, and the seal mechanism encrypts the key ring. | no | yes | no | The row has the seal mechanism encrypting the root key, and the root key encrypting the key ring; the claim swaps the roles. |
| 29 | `P09` | The telemetry metrics table reports non-entity counts as a `summary` metric, and the value counts the number of distinct non entities that created a token during the last month. | no | no | no | The row's metric type is gauge and the window is 'the configured reporting period', not the last month. |
| 30 | `P10` | The shards from init reconstruct the root key directly, and the root key then decrypts the unseal key. | no | yes | no | Both links are backwards relative to the chunk: shares rebuild the unseal key, which decrypts the root key. |

## Agreement with the hand labels

| layer | judged | raw agreement | precision | recall | Cohen's kappa |
|---|---|---|---|---|---|
| NLI cross-encoder | 30 | 0.833 | 0.826 | 0.950 | 0.595 |
| LLM judge | 30 | 0.933 | 1.000 | 0.900 | 0.857 |

## Confusion matrices

**NLI vs human** — 30 judged, 0 not judged

| | human: supported | human: unsupported |
|---|---|---|
| **judge: supported** | 19 (TP) | 4 (FP) |
| **judge: unsupported** | 1 (FN) | 6 (TN) |

**LLM judge vs human** — 30 judged, 0 not judged

| | human: supported | human: unsupported |
|---|---|---|
| **judge: supported** | 18 (TP) | 0 (FP) |
| **judge: unsupported** | 2 (FN) | 10 (TN) |

## NLI x judge on the same claim

| | judge: supported | judge: unsupported |
|---|---|---|
| **NLI: supported** | 18 | 5 |
| **NLI: unsupported** | 0 | 7 |

The same grid is written to `notes/judge-confusion.csv` for the report.

## Cost and calls

| item | value |
|---|---|
| judge model | `deepseek-v4-pro` |
| judge verdicts stored (one call each) | 30 |
| judge tokens in / out | 23841 / 4924 |
| judge cost at configured prices | $0.0065 / ¥0.0436 |
| judge price in / out (USD per Mtok) | 0.15 / 0.6 |
| NLI calls | 30 (local, free) |
| NLI threshold | 0.5 |
<!-- END GENERATED: judge calibration tables -->

## The decision

**The hosted judge gates the headline citation numbers. The NLI layer does not.**

- `deepseek-v4-pro` clears the bar at kappa 0.857 (agreement 0.933, precision 1.000,
  recall 0.900). Its two misses are both false negatives on true claims: the
  chain-compression claim (C-A009-c3) and the replication sentence that appears at the
  very end of a long chunk (C-A006-c3). Both are claims a careful reader accepts and
  a strict reader can argue with, which is the honest description of this layer: it is
  conservative, not sloppy. It made no false-positive call in 30 rows.
- The NLI cross-encoder **misses the bar**: kappa 0.595 against 0.60, with agreement
  0.833, precision 0.826 and recall 0.950. Its four false positives are the
  `reload`-defaults-to-`1m` distractor, the reversed unseal/root key direction, the
  reversed table row, and the reversed shard chain — i.e. it accepts exactly the
  relation-reversal and in-chunk-distractor drifts, which is the failure mode that
  would inflate citation precision if it were allowed to gate.

Two things must be said about that near-miss, because the difference is smaller than
the threshold makes it look. First, with 30 rows the standard error of kappa is
roughly ±0.18; 0.595 and 0.60 are the same number measured once. The decision does
not rest on the gap. It rests on the direction of the errors: every disagreement
between the two layers is `nli_only` (five claims the NLI accepts and the judge
rejects; there is not one the judge accepts and the NLI rejects), so NLI's mistakes
are one-sided and inflate support. A layer whose only errors push the headline number
up cannot be the gate for it, whatever its kappa.

**What that means for the pipeline as wired.** `SupportJudges.judge_claim` requires
that no layer says False, so the combined verdict is a conjunction. On this set there
is no claim the NLI layer rejects and the judge accepts (`judge_only` is 0), so the
conjunction is identical to the judge's own verdict — the NLI layer adds 30 local,
free calls and changes no headline number. That is the argument for keeping NLI as a
cheap screen with the judge as the reference: the NLI layer alone would report
citation precision on 23 of 30 claims where the hand labels support 20, and running
both gives the judge's numbers with a veto that can only cost recall. Reporting
should quote the judge layer, mention the NLI layer as an independent second opinion,
and say that the two disagree on 5 of 30 claims, always in the permissive direction.

## Cost and calls, per configuration

The calibration itself: 30 hosted judge calls, 23,841 tokens in and 4,924 out,
$0.0065 / ¥0.0436 at the configured $0.15 in and $0.60 out per million tokens —
about $0.00022 per claim, or ¥0.15 per 1,000 claims. The NLI calls are local and
free; 30 of them ran.

Three probe calls (not part of the calibration) measured the cheap setting described
above: `reasoning_effort: "none"` costs $0.0002 per call on the gateway's own
list price against $0.00037 with deliberation, a factor of 1.8, for the same verdict
on a claim that needs no deliberation.

For a full run rather than a calibration sample, `configs/judge_smoke.yaml` runs the
same two layers over the fixture corpus with the generation stub, so the wiring is
checkable end to end. Its run, `runs/judge-smoke-20261030T122905-b67fc09f`, writes
`grounding.judge_confusion = {both_supported: 4, nli_only: 0, judge_only: 1,
neither: 0}` into `metrics.json`, plus a `judge` entry in `system.cost_components`
(1,963 tokens in, 747 out, $0.000743 / ¥0.0050 for 5 judge calls and 5 local NLI
calls) and per-layer call counts in `models.json`. That run is also a useful
counter-example: on stub claims, which are verbatim chunk fragments, the one
disagreement runs `judge_only` — the hosted judge accepting what the NLI layer
called neutral — so "NLI is the permissive one" is a property of the real claims
above, not of the layers in general.

## What this does not establish

- n = 30 on one corpus (Vault 1.21.x) with one generator and one chunking strategy.
  Enough for a decision between two layers, not enough for a point estimate to two
  decimal places.
- Judge specificity is measured against the ten constructed drifts, not against
  natural generator errors, because this pipeline produced no contained-but-false
  claims in 47 attempts. If the generator were weaker — or containment were looser —
  the false-positive rate would be measured on harder material.
- Only two of the 30 rows come from an unanswerable golden item (U005), so this says
  nothing about abstention or about claims made when the knowledge base has no answer.
- The judge is one model at one temperature. Nothing here supports a claim about
  `deepseek-v4-pro` in general, only about this prompt, this chunk size and this
  corpus.

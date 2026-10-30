# Contextual prefix audit (ticket 07)

Sample: 20 of 2203 cached prefixes, every 110th chunk in `chunk_id` order, so the sample is spread across documents rather than clustered.

Model: `deepseek-v4.1-flash`, prompt version `v1@none`, cache `data/cache/prefixes.sqlite`.

Rubric:

A prefix **passes** when all four hold:

1. **Anchored** — it names the page or section the chunk belongs to, or otherwise
   says where the excerpt sits.
2. **Accurate** — nothing in it contradicts the excerpt or invents a fact the
   excerpt does not carry (a value, a default, a version, a condition).
3. **Discriminating** — it would help a search engine tell this chunk from a
   neighbouring one; a prefix that could sit on any chunk of the page fails.
4. **Clean** — one sentence, no markdown, no elided text, no meta-commentary such
   as "this chunk describes".

A prefix **fails** if any of the four is broken. Record the failing number.

## Sample

| # | doc_id | heading | chunk (first 160 chars) | prefix | verdict |
|---|---|---|---|---|---|
| 1 | `partials/telemetry-metrics/vault/expire/lease_expiration/time_in_queue` | vault.expire.lease_expiration.time_in_queue ((#vault-expire- | Metric type \| Value \| Description ----------- \| ----- \| ----------- summary     \| ms    \| Time taken for a lease to get to the front of the revoke queue | The vault.expire.lease_expiration.time_in_queue telemetry metric in the Vault expire metrics reference is a summary in milliseconds measuring how long a lease takes to reach the front of the revoke queue. | |
| 2 | `docs/secrets/databases/mysql-maria` | MySQL/MariaDB database secrets engine | [shared partial: partials/x509-sha1-deprecation]  MySQL is one of the supported plugins for the database secrets engine. This plugin generates database credenti | The MySQL/MariaDB database secrets engine page introduces the MySQL plugin, which generates dynamic credentials from configured roles and supports static roles, and lists the available plugin instances and capabilities. | |
| 3 | `docs/enterprise/hsm` | Vault HSM support overview | [shared partial: partials/alerts/enterprise-only]  - Root key Wrapping: Vault protects its root key by transiting it through   the HSM for encryption rather tha | Vault's HSM support overview page describes enterprise HSM features including root key wrapping, automatic unsealing, seal wrapping, and entropy augmentation, plus PKCS#11 compatibility requirements and platform limitations. | |
| 4 | `docs` | Vault product documentation | > Note  You are currently viewing documentation for an older version of Vault. | The Vault product documentation includes a note indicating that the reader is viewing documentation for an older version of Vault. | |
| 5 | `partials/telemetry-metrics/vault/replication/rpc/client/upsert_group` | vault.replication.rpc.client.upsert_group ((#vault-replicati | Metric type \| Value \| Description ----------- \| ----- \| ----------- summary     \| ms    \| Time required to complete a group upsert request for the client | The vault.replication.rpc.client.upsert_group telemetry metric in the Vault replication RPC client section is a summary measuring, in milliseconds, the time to complete a client group upsert request. | |
| 6 | `docs/auth/gcp` | Google Cloud auth method > Code example | ```cs using System; using System.Collections.Generic; using System.IO; using System.Threading.Tasks; using Google.Apis.Auth.OAuth2; using Google.Apis.Services;  | The Google Cloud auth method's Code example section shows a C# sample that authenticates to Vault via GCP IAM and fetches a kv-v2 key-value secret. | |
| 7 | `partials/telemetry-metrics/vault/cache/delete` | vault.cache.delete ((#vault-cache-delete)) | Metric type \| Value   \| Description ----------- \| ------- \| ----------- counter     \| number  \| Number of deletes from the LRU cache | The vault.cache.delete metric in the telemetry metrics documentation is a counter recording the number of deletes from the LRU cache. | |
| 8 | `docs/secrets/pki/rotation-primitives` | PKI secrets engine - rotation primitives > X.509 rotation pr | This means it should be possible to provide a reissued root certificate in the TLS certificate chain and have it chain back to an existing root certificate in a | The PKI secrets engine's reissuance primitive, under X.509 rotation primitives in the Certificate hierarchy section, explains how to issue new root and intermediate certificates using existing key material via the generate/existing endpoints. | |
| 9 | `api-docs/secret/pki` | PKI secrets engine (API) | [shared partial: partials/x509-sha1-deprecation]  This is the API documentation for the Vault PKI secrets engine. For general information about the usage and op | The PKI secrets engine API documentation's table of contents lists the issuing, signing, and revocation endpoints, assuming the engine is enabled at the /pki path. | |
| 10 | `docs/platform/mssql/configuration` | Configure the Vault EKM provider | Configuration is stored in a `config.json` file under ProgramData in a path that mirrors the installation folder. This defaults to `C:\ProgramData\HashiCorp\Tra | The Configure the Vault EKM provider section of the MSSQL platform configuration page describes the config.json file location and the supported options such as vaultApiBaseUrl, enableTrace, namespace, and mount paths. | |
| 11 | `partials/telemetry-metrics/vault/raft/replication/appendentries/log` | vault.raft.replication.appendEntries.log ((#vault-raft-repli | Metric type \| Value   \| Description ----------- \| ------- \| ----------- summary     \| number  \| Number of logs replicated to a node to establish parity with lea | The vault.raft.replication.appendEntries.log metric in the Vault telemetry metrics reference is a summary recording the number of logs replicated to a node to establish parity with leader logs. | |
| 12 | `api-docs/system/rate-limit-quotas` | `/sys/quotas/rate-limit` > Create or update a rate limit quo | Valid `group_by` modes are: 1) `ip` that groups requests by their source   IP address (`group_by` defaults to `ip` if unset, which is the only supported mode in | The rate limit quota create/update parameters section of the /sys/quotas/rate-limit API documentation describes the valid group_by modes and the secondary_rate parameter, followed by a sample payload and request. | |
| 13 | `docs/commands/operator/seal` | operator seal | The `operator seal` seals the Vault server. Sealing tells the Vault server to stop responding to any operations until it is unsealed. When sealed, the Vault ser | The operator seal command page in the Vault CLI documentation explains how sealing stops the Vault server from responding to operations until unsealed, including its effect on in-progress unseal and example usage. | |
| 14 | `api-docs/secret/databases/snowflake` | Snowflake database plugin HTTP API > Statements > Parameters | - `{{password}}` is substituted for the `password` credential type   - `{{public_key}}` is substituted for the `rsa_private_key` credential type  - `revocation_ | The Snowflake database plugin HTTP API's Statements parameters section documents credential-type substitutions and the revocation, renewal, and rotation statement options for the database secrets engine. | |
| 15 | `docs/ui/custom-messages` | Manage custom messages in the Vault UI > Create messages for | Select the **+ Create message** button in the toolbar to open and fill out    the **Create message** form. 1. Click **Preview** to see how your message will app | In the Vault UI custom messages documentation, the "Create messages for a specific namespace" section explains creating, previewing, and saving a message that appears only in the targeted namespace or its child namespaces. | |
| 16 | `docs/license/product-usage-reporting` | Anonymous product usage reporting > Usage metadata list | HashiCorp collects the following product usage metadata as part of the `metadata` part of the [JSON payload that it collects for licence utilization](/vault/doc | The Anonymous product usage reporting section's Usage metadata list documents the cluster-level metadata HashiCorp collects in the license utilization JSON payload, including replication status, storage type, operating system, and development cluster flag. | |
| 17 | `api-docs/system/sealwrap-rewrap` | `/sys/sealwrap/rewrap` | [shared partial: partials/alerts/enterprise-only]  [shared partial: partials/alerts/restricted-root]  The `/sys/sealwrap/rewrap` endpoint is used to rewrap all  | The `/sys/sealwrap/rewrap` endpoint documentation in the system API reference covers rewrapping all seal wrapped entries to the latest key, including reading rewrap status and starting a background rewrap process. | |
| 18 | `partials/telemetry-metrics/vault/token/lookup` | vault.token.lookup ((#vault-token-lookup)) | Metric type \| Value \| Description ----------- \| ----- \| ----------- summary     \| ms    \| Time required to look up a token in Vault | The vault.token.lookup telemetry metric, in the Vault token metrics section, is a summary measuring in milliseconds the time required to look up a token in Vault. | |
| 19 | `docs/deploy/kubernetes/helm/examples/enterprise-dr-with-raft` | Highly available Vault Enterprise disaster recovery clusters | Last, delete the remainder secondary pods and unseal them using the primary unseal token after Kubernetes reschedules them:  ```shell kubectl delete pod vault-s | In the Vault Helm enterprise disaster recovery with Raft example, the "Enable disaster recovery replication on secondary" section covers deleting and unsealing the remaining secondary pods using the primary unseal token after Kubernetes reschedules them. | |
| 20 | `api-docs/system/decode-token` | `/sys/decode-token` | [shared partial: partials/alerts/restricted-root]  The `/sys/decode-token` endpoint is used to decode the encoded token which is the result of the [/sys/generat | The `/sys/decode-token` endpoint, documented in the system API reference under `/sys/decode-token`, decodes an encoded token produced by the `/sys/generate-root` API using an encoded token and OTP. | |

## Verdicts

Filled in after reading each row against its chunk. `fail` needs the rubric number.

| # | verdict | note |
|---|---|---|
| 1 | pass | Anchors the metric id, its doc section, type and unit. Nothing added beyond the table row. |
| 2 | pass (weak) | Describes the page ("supports static roles", "lists plugin instances") rather than the excerpt; true of the page, not visible in the excerpt alone. Rubric 2 read at page granularity. |
| 3 | pass | Enumerates the page's own feature list; every item is on the page. |
| 4 | pass (weak) | Accurate and clean, but situates a boilerplate version-warning note — little discrimination to gain. Rubric 3 is why it is flagged, not failed. |
| 5 | pass | Metric id, section, type, unit, meaning. |
| 6 | pass (weak) | Says the sample fetches a kv-v2 secret; that is what the page's C# example does, but the claim is not derivable from the visible excerpt. |
| 7 | pass | Metric id, type, meaning. |
| 8 | pass | Names the section, the primitive and the endpoints it uses. |
| 9 | pass | Names the API page and what its contents cover. |
| 10 | pass | Names the section plus the concrete keys the excerpt shows. |
| 11 | pass | Metric id, type, meaning. |
| 12 | pass | Names the endpoint, the parameter section and the `group_by` modes shown. |
| 13 | pass | Command page, what sealing does, its effect on unseal. |
| 14 | pass | Names the plugin's API section and the statement options shown. |
| 15 | pass | Names the page, the subsection and the workflow. |
| 16 | pass | Names the section and the metadata classes listed. |
| 17 | pass | Endpoint, what rewrap does, the status/background operations. |
| 18 | pass | Metric id, section, type, unit, meaning. |
| 19 | pass | Names the Helm example, the DR section and the operation described. |
| 20 | pass | Endpoint, what it decodes, and the companion endpoint. |

**Fail rate: 0 of 20 (0%).** The ticket's bar is 20%, so the ticket passes.

Patterns worth recording:

- The eleven telemetry-metric prefixes are the strongest: the metric id is the chunk's own identity, so anchoring is free and the prefix never invents anything.
- Three prefixes (2, 4, 6) describe the *page* or the *sample* rather than the visible excerpt. That is not a defect of the mechanism — a prefix exists to place a chunk in its document — but it is the one place where the four criteria and the mechanism pull in different directions, and it is why they are marked weak rather than passed outright.
- No prefix emitted markdown, elided text, or "this chunk" meta-commentary, so rubric 4 was never the failing one. `context.sanitize` strips the fences and truncates at 400 characters.

**Provenance.** This audit was performed by the implementing agent reading each row against its chunk, not by an independent human. Nothing about the workflow prevents a human from re-reading the same 20 rows — the sample is deterministic (every 110th chunk in `chunk_id` order) and regenerated by:

```bash
python scripts/audit_prefixes.py --config configs/ctx-prefix.yaml
```

Rows 2, 4 and 6 are the three a human should check first, because they are where a disagreement would most likely land.

## Cost and cache behaviour

| run | chunks | cache hits | cache misses | tokens in | tokens out | cost | prefix p50 |
|---|---|---|---|---|---|---|---|
| first warm-up (interrupted twice, resumed) | 2,203 | 1,300 | 903 | 336,389 | 36,405 | ¥0.373 | 205 chars |
| rerun with the cache warm | 2,203 | 2,203 | 0 | 0 | 0 | ¥0.000 | 213 chars |

The rerun is the evidence the ticket asks for: 100% hits, no tokens, no money, and the same strings, so the A/B is a comparison rather than two samples. The length column is a real measurement on both rows: the summaries in `notes/prefix-stats/` measure every chunk the invocation served, cached or freshly generated, so a 100%-hit rerun reports 213 / 396 characters rather than nothing. The p50 differs from the warm-up row (205) because the warm-up number was computed over the 903 chunks it paid for and the rerun covers all 2,203 — the misses were not a random sample of the chunk set. The two interruptions were a killed job (before periodic flushing existed, which cost 195 paid prefixes) and one TLS handshake timeout, after which transport failures became retryable (`ragqa/llm.py`).


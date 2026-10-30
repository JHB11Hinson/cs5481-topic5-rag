# Near-miss items at the chosen working point

A near-miss is a golden item that is deliberately unanswerable but topically adjacent: the retrieval score for it looks like the score for a real question. Each item below is shown with the decision its score produces at that mode's chosen threshold and with the top three retrieved chunks, so the reader can see whether the score that was (or was not) sufficient actually pointed at the passage that nearly answered the question.

Each item also reports the decision the run itself took (`run-time abstained`), which can differ from the score-policy decision above it: in the `llm` runs the model declines items whose score clears the threshold, and in the `hybrid` runs the score threshold was set below every observed score, so the run abstained for a different reason or not at all.

| mode | t | raw threshold | answerable answered | near-miss answered | over-abstain | under-abstain |
|---|---|---|---|---|---|---|
| hybrid | 0.4059 | 0.030432 | 10/10 | 8/10 | 0.0000 | 0.8000 |
| rerank | 0.4471 | 0.75925 | 10/10 | 4/10 | 0.0000 | 0.4000 |
| llm | 0.4471 | 0.75925 | 10/10 | 4/10 | 0.0000 | 0.4000 |

## hybrid

Scale: RRF fused sum, ~1/(rrf_k + rank); with rrf_k=60 and k=10 the observed range is about [0.015, 0.035], so no threshold in [0.2, 0.9] is reachable raw. Working point: t=0.4059 normalized = raw 0.030432. Decision rule: answer iff normalized(top score) >= t.

### U001 — ANSWERED — under-abstention (normalized 0.6395 >= t 0.4059)

- question: What is the default value of the -namespace flag for vault operator init in Vault 1.22?
- run: `real-hybrid-20261030T092148-08d22872` · top raw score 0.032522 · run-time abstained: False
- top retrieved chunks:

  1. `c-337c1bcdd974f3f9` · docs/commands/server · raw 0.032522
     > The `server` command starts a Vault server that responds to API requests. By default, Vault will start in a "sealed" state. The Vault cluster must be initialized before use, usually by the `vault oper …

  2. `c-05ccf2b0a924b651` · docs/deploy/kubernetes/vso/api-reference · raw 0.031746
     > If no namespace prefix is provided it will default to the namespace of the VaultAuth CR. If no value is specified for VaultAuthRef the Operator will default to the `default` VaultAuth, configured in t …

  3. `c-b0c6c4fac8c8ea3d` · docs/deploy/kubernetes/vso/api-reference · raw 0.029631
     > | Field | Description | Default | Validation | | --- | --- | --- | --- | | `role` _string_ | Role to use for authenticating to Vault. | | | | `serviceAccount` _string_ | ServiceAccount to use when aut …

### U005 — ANSWERED — under-abstention (normalized 0.6395 >= t 0.4059)

- question: What is the Terraform resource name for the Vault AWS auth backend?
- run: `real-hybrid-20261030T092148-08d22872` · top raw score 0.032522 · run-time abstained: False
- top retrieved chunks:

  1. `c-20f172e9e24f411b` · docs/deploy/kubernetes/vso/sources/vault/auth/aws · raw 0.032522
     > The Vault Secrets Operator (VSO) supports [AWS authentication](/vault/docs/auth/aws) when accessing Vault. VSO can retrieve AWS credentials: - from an [IRSA-enabled Kubernetes service account][aws-irs …

  2. `c-e73d9d1c0d090ddd` · docs/configuration/programmatic-management · raw 0.031258
     > Use Terraform to manage policies, namespaces, and plugins in Vault. ## Before you start - **You must have [Terraform installed](/terraform/install)**. - **You must have the [Terraform Vault provider]( …

  3. `c-ff7430c7488ed19a` · api-docs/secret/terraform · raw 0.030679
     > This is the API documentation for the Vault Terraform Cloud secret backend. For general information about the usage and operation of the Terraform Cloud backend, please see the [Vault Terraform Cloud …

### U006 — ANSWERED — under-abstention (normalized 0.6395 >= t 0.4059)

- question: What is the Docker image digest for the Vault 1.20.4 release?
- run: `real-hybrid-20261030T092148-08d22872` · top raw score 0.032522 · run-time abstained: False
- top retrieved chunks:

  1. `c-a347843a39bd6544` · docs/updates/deprecation · raw 0.032522
     > | Announced | Expected end of support | Expected removal | | :-------: | :---------------------: | :--------------: | | SEP 2023 | CY24 Q2 | CY24 Q2 Vault no longer provides official support for the C …

  2. `c-ffddcbba6b9be254` · docs/deploy/kubernetes/helm/configuration · raw 0.031498
     > This is required when using auto-tls and more than 1 replica. - `image` - Values that configure the Vault Agent Injector Docker image. - `repository` (`string: "hashicorp/vault-k8s"`) - The name of th …

  3. `c-47677bb90d3bb738` · docs/deploy/kubernetes/helm/configuration · raw 0.028778
     > - `pullPolicy` (`string: "IfNotPresent"`) - The pull policy for agent image. The default pull policy is `IfNotPresent` which causes the Kubelet to skip pulling an image if it already exists. - `reposi …

## rerank

Scale: cross-encoder score in [0, 1], clustered high: answerable items in the runs on disk score 0.77-1.00 while near-misses reach 0.97. Working point: t=0.4471 normalized = raw 0.75925. Decision rule: answer iff normalized(top score) >= t.

### U005 — ANSWERED — under-abstention (normalized 0.7483 >= t 0.4471)

- question: What is the Terraform resource name for the Vault AWS auth backend?
- run: `real-rerank-20261030T095541-a6eb2d5e` · top raw score 0.965412 · run-time abstained: False
- top retrieved chunks:

  1. `c-20f172e9e24f411b` · docs/deploy/kubernetes/vso/sources/vault/auth/aws · raw 0.965412
     > The Vault Secrets Operator (VSO) supports [AWS authentication](/vault/docs/auth/aws) when accessing Vault. VSO can retrieve AWS credentials: - from an [IRSA-enabled Kubernetes service account][aws-irs …

  2. `c-aef0ec737c000f2f` · docs/deploy/kubernetes/vso/sources/vault/auth/gcp · raw 0.895369
     > The Vault Secrets Operator (VSO) supports authenticating to Vault's [GCP auth](/vault/docs/auth/gcp) method, using Google's Kubernetes Engine (GKE) workload identity. 1. Follow Google's [Use Workload …

  3. `c-e73d9d1c0d090ddd` · docs/configuration/programmatic-management · raw 0.887568
     > Use Terraform to manage policies, namespaces, and plugins in Vault. ## Before you start - **You must have [Terraform installed](/terraform/install)**. - **You must have the [Terraform Vault provider]( …

### U007 — ANSWERED — under-abstention (normalized 0.6951 >= t 0.4471)

- question: Which Kubernetes admission controller should be disabled when running the Vault agent injector?
- run: `real-rerank-20261030T095541-a6eb2d5e` · top raw score 0.924579 · run-time abstained: False
- top retrieved chunks:

  1. `c-8bf6e9016c1e01aa` · docs/deploy/kubernetes/injector · raw 0.924579
     > The Vault Agent Injector alters pod specifications to include Vault Agent containers that render Vault secrets to a shared memory volume using [Vault Agent Templates](/vault/docs/agent-and-proxy/agent …

  2. `c-e05b3691a38eebcd` · docs/deploy/kubernetes/injector/installation · raw 0.871551
     > The [Vault Helm chart](/vault/docs/platform/k8s/helm) is the recommended way to install and configure the Agent Injector in Kubernetes. ~> The Vault Agent Injector requires Vault 1.3.1 or greater. To …

  3. `c-ffddcbba6b9be254` · docs/deploy/kubernetes/helm/configuration · raw 0.770045
     > This is required when using auto-tls and more than 1 replica. - `image` - Values that configure the Vault Agent Injector Docker image. - `repository` (`string: "hashicorp/vault-k8s"`) - The name of th …

### U001 — ANSWERED — under-abstention (normalized 0.6471 >= t 0.4471)

- question: What is the default value of the -namespace flag for vault operator init in Vault 1.22?
- run: `real-rerank-20261030T095541-a6eb2d5e` · top raw score 0.890433 · run-time abstained: False
- top retrieved chunks:

  1. `c-3becd3bb1a1aaa30` · docs/commands/operator/init · raw 0.890433
     > The `operator init` command initializes a Vault server. Initialization is the process by which Vault's storage backend is prepared to receive data. Since Vault servers share the same storage backend i …

  2. `c-05ccf2b0a924b651` · docs/deploy/kubernetes/vso/api-reference · raw 0.792020
     > If no namespace prefix is provided it will default to the namespace of the VaultAuth CR. If no value is specified for VaultAuthRef the Operator will default to the `default` VaultAuth, configured in t …

  3. `c-337c1bcdd974f3f9` · docs/commands/server · raw 0.705537
     > The `server` command starts a Vault server that responds to API requests. By default, Vault will start in a "sealed" state. The Vault cluster must be initialized before use, usually by the `vault oper …

## llm

Scale: same cross-encoder score as rerank; generation is an LLM, but the abstain threshold is still compared against the retrieval score. Working point: t=0.4471 normalized = raw 0.75925. Decision rule: answer iff normalized(top score) >= t.

### U005 — ANSWERED — under-abstention (normalized 0.7483 >= t 0.4471)

- question: What is the Terraform resource name for the Vault AWS auth backend?
- run: `real-llm-20261030T113604-a5c0a3e4` · top raw score 0.965412 · run-time abstained: False
- top retrieved chunks:

  1. `c-20f172e9e24f411b` · docs/deploy/kubernetes/vso/sources/vault/auth/aws · raw 0.965412
     > The Vault Secrets Operator (VSO) supports [AWS authentication](/vault/docs/auth/aws) when accessing Vault. VSO can retrieve AWS credentials: - from an [IRSA-enabled Kubernetes service account][aws-irs …

  2. `c-aef0ec737c000f2f` · docs/deploy/kubernetes/vso/sources/vault/auth/gcp · raw 0.895369
     > The Vault Secrets Operator (VSO) supports authenticating to Vault's [GCP auth](/vault/docs/auth/gcp) method, using Google's Kubernetes Engine (GKE) workload identity. 1. Follow Google's [Use Workload …

  3. `c-e73d9d1c0d090ddd` · docs/configuration/programmatic-management · raw 0.887568
     > Use Terraform to manage policies, namespaces, and plugins in Vault. ## Before you start - **You must have [Terraform installed](/terraform/install)**. - **You must have the [Terraform Vault provider]( …

### U007 — ANSWERED — under-abstention (normalized 0.6951 >= t 0.4471)

- question: Which Kubernetes admission controller should be disabled when running the Vault agent injector?
- run: `real-llm-20261030T113604-a5c0a3e4` · top raw score 0.924579 · run-time abstained: True
- top retrieved chunks:

  1. `c-8bf6e9016c1e01aa` · docs/deploy/kubernetes/injector · raw 0.924579
     > The Vault Agent Injector alters pod specifications to include Vault Agent containers that render Vault secrets to a shared memory volume using [Vault Agent Templates](/vault/docs/agent-and-proxy/agent …

  2. `c-e05b3691a38eebcd` · docs/deploy/kubernetes/injector/installation · raw 0.871551
     > The [Vault Helm chart](/vault/docs/platform/k8s/helm) is the recommended way to install and configure the Agent Injector in Kubernetes. ~> The Vault Agent Injector requires Vault 1.3.1 or greater. To …

  3. `c-ffddcbba6b9be254` · docs/deploy/kubernetes/helm/configuration · raw 0.770045
     > This is required when using auto-tls and more than 1 replica. - `image` - Values that configure the Vault Agent Injector Docker image. - `repository` (`string: "hashicorp/vault-k8s"`) - The name of th …

### U001 — ANSWERED — under-abstention (normalized 0.6471 >= t 0.4471)

- question: What is the default value of the -namespace flag for vault operator init in Vault 1.22?
- run: `real-llm-20261030T113604-a5c0a3e4` · top raw score 0.890433 · run-time abstained: True
- top retrieved chunks:

  1. `c-3becd3bb1a1aaa30` · docs/commands/operator/init · raw 0.890433
     > The `operator init` command initializes a Vault server. Initialization is the process by which Vault's storage backend is prepared to receive data. Since Vault servers share the same storage backend i …

  2. `c-05ccf2b0a924b651` · docs/deploy/kubernetes/vso/api-reference · raw 0.792020
     > If no namespace prefix is provided it will default to the namespace of the VaultAuth CR. If no value is specified for VaultAuthRef the Operator will default to the `default` VaultAuth, configured in t …

  3. `c-337c1bcdd974f3f9` · docs/commands/server · raw 0.705537
     > The `server` command starts a Vault server that responds to API requests. By default, Vault will start in a "sealed" state. The Vault cluster must be initialized before use, usually by the `vault oper …

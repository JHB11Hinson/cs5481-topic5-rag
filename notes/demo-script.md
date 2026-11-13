# Demo script: a citation you can click, and an abstention you can inspect

Ticket 16. One screen, one configuration, five questions. Every answer on the
screen was produced by the pipeline `ragqa.run` measures, and every claim carries
a citation marker that opens the source span it rests on.

The outputs below are captured from a real session, not written by hand. Ticket 16
requires the script to work as a fallback if the live model is unavailable, so it
records three things: what to type, what appears, and which of the two offline
paths to take when the gateway or the GPU is not there.

## Setup

```bash
cd <repo root>
python -m ragqa serve --config configs/real_llm.yaml     # the real demo
```

The process loads the corpus, chunks, bge-m3, the Qdrant collection, the BM25
branch, the reranker and the generator **once**, then serves. Startup on this
machine: 38.9 s, 2,203 chunks. Nothing is reloaded per question, and the opening
message states exactly what is being served:

```
**Configuration `real-llm`** - snapshot `vault-1.21.x-1817bdfe`, 2203 chunks,
`recursive_parent_child` chunking, `rerank` retrieval (k=10), embeddings
`BAAI/bge-m3`, generator `deepseek-v4.1-flash`, index `qdrant`. Loaded once in
38.9s.
```

Chainlit listens on `http://localhost:8000` (`CHAINLIT_PORT` overrides it).
`configs/real_llm.yaml` needs `LLM_BASE_URL` and `LLM_API_KEY` in the environment or
in `.env`; `data/` must hold the corpus, the embedding cache and the index.

### When the live model is unavailable

Two offline paths, in order of fidelity:

1. **Replay from the generation cache** (same configuration, same answers, no
   network): every request is cached by content hash in `data/cache/llm.sqlite`, so
   re-asking a question that was asked before returns the stored JSON. The footer
   shows it: `generation 1 ms`. This is how the outputs below were re-captured for
   this document.
2. **The fixture configuration** (no network, no GPU, no model weights at all):
   `python -m ragqa serve --config configs/smoke.yaml`. Eleven fixture chunks, a
   hashed embedder, an in-memory index, a stub generator. The screen, the markers
   and the abstention path are identical; the answers are not the Vault answers.
   This is the path to use if the demo machine has neither a GPU nor a network.

## How a citation click works

The marker is an `Action`, not a link. Clicking `[1]` sends `open_citation` with the
citation payload (`marker`, `claim_id`, `chunk_id`, `doc_id`, `span_start`,
`span_end`); the handler rebuilds the panel from the index and sends a
`CitationCard` custom element to the side panel. The payload carries no chunk text
on purpose: the panel is always assembled from the chunk as it exists in this
process, so a click cannot show a stale copy of the evidence.

Under Chainlit 2.3.0 a custom element is rendered by fetching
`/public/elements/CitationCard.jsx` and evaluating it in the browser, so the
renderer ships in `public/elements/` and receives the panel as `props`. The cited
span arrives already escaped, with the cited characters wrapped in `<mark>`.

Panel content for A001 `[1]`, captured from the running process:

```
marker:       [1]
doc_title:    Seal/Unseal
heading_path: Seal/Unseal
url:          https://developer.hashicorp.com/vault/docs/concepts/seal
chunk_id:     c-2e02db0a352ce89c
span_text:    "When you start a Vault server, it starts in a sealed state."
chunk_html:   <mark>When you start a Vault server, it starts in a sealed state.</mark>
              In this state, Vault can access the physical storage, but it cannot
              decrypt any of the data on it.
```

## The five questions

Commands used for every block below (`configs/real_llm.yaml`, worktree root):

```bash
python .scratch/capture_demo.py configs/real_llm.yaml .scratch/demo-capture.json
```

The capture script builds one `ChatEngine`, asks the five questions in order, prints
`demo.render_answer(...)` for each and writes the raw responses to JSON. The blocks
below are that output verbatim; only the latencies differ between captures, and the
first question always pays for the reranker's first load (11 s here, 0.7-4.7 s after
that).

### Verifying the click path without a browser

`python .scratch/drive_chainlit.py` replaces the websocket with a recording emitter
and calls the registered `on_chat_start`, `on_message` and `open_citation` handlers
directly, then prints the action payload a marker carries and the props the panel
receives. That is how the panel content quoted above was read off the running code
rather than assumed.

### 1. A001 - a claim per sentence, three markers

> What state does a Vault server start in, and what can it not do in that state?

```
**Answer** - 3 of 3 claims carry a verified citation.
1. A Vault server starts in a sealed state. [1]
2. In the sealed state, Vault can access physical storage but cannot decrypt any of the data on it. [2]
3. Prior to unsealing, the only possible Vault operations are to unseal the Vault and check the status of the server. [3]

---
_Retrieval 11111 ms | generation 3 ms | configuration `real-llm`_
```

Point at: three markers, three different spans - click `[2]` and the highlighted
sentence is the second claim, not the first. All three happen to file the seal
document; the panel still opens the exact chunk the claim was checked against.

### 2. A004 - the shortest possible answer

> What address and port does the Vault dev server listen on by default?

```
**Answer** - 1 of 1 claims carry a verified citation.
1. The Vault dev server listens on 127.0.0.1:8200 by default, without TLS. [1]

---
_Retrieval 4676 ms | generation 1 ms | configuration `real-llm`_
```

Panel: `Dev Server Mode > "Dev" server mode`,
`https://developer.hashicorp.com/vault/docs/concepts/dev-server`, top score 0.990.

### 3. A007 - a table row, not prose

> According to the entropy augmentation table, what is the root key encrypted by, and what does it encrypt?

```
**Answer** - 1 of 1 claims carry a verified citation.
1. The root key is an AES key encrypted by the seal mechanism, and it encrypts the key ring. [1]

---
_Retrieval 4617 ms | generation 2 ms | configuration `real-llm`_
```

Panel: `Augment entropy with external sampling`,
`https://developer.hashicorp.com/vault/docs/enterprise/entropy-augmentation`. This is
the case a fixed word window breaks: the claim comes from a table, and the
`recursive_parent_child` chunk kept the table whole.

### 4. A009 - the pipeline refusing part of its own answer

> During operator init the root key is split into shards; how does that relate to the sealed state a server starts in?

```
**Answer** - 2 of 3 claims carry a verified citation.
1. A Vault server starts in a sealed state, where it can access physical storage but cannot decrypt data on it. [1]
2. A threshold of shards is required to reconstruct the root key, which is then used to decrypt Vault's encryption key, connecting the init-created shares to the unsealing needed after a server starts sealed. [2]

**Withheld - citation did not contain the claim:**
- During operator init, the default configuration uses Shamir's Secret Sharing to split the root key into a configured number of shards, also called key shares or unseal keys. - `quote_not_in_chunk`, citing `c-3becd3bb1a1aaa30` (quoted text does not occur in the cited chunk)

---
_Retrieval 4631 ms | generation 17488 ms | configuration `real-llm`_
```

Point at: the third claim is plausible and probably true, and it is still withheld -
the quote the model returned is not in the chunk it cited, so containment failed
before any judge was consulted (`ADR-0004`). The screen shows the failure class
rather than quietly dropping the claim, and the claim gets no marker, because there
is no span to open.

### 5. U008 - the near miss that abstains

> If my AppRole secret ID has a 30-minute TTL, what will the agent auto-auth token TTL be?

```
**The knowledge base does not contain an answer to this question. What follows is general knowledge from the model, not from these documents: it carries no citation and should be checked against a current source.**

<one paragraph of the model's own general prose — capture the live text before
presenting it; only the note above it and the placement below are fixed>

_To check: <the model's one line on what to verify>_

The closest page is **Vault Secrets Operator API Reference** › API Reference › secrets.hashicorp.com/v1beta1 › Resource Types › VaultAppRoleSecretID.

> using tokens generated by this secret ID. | | | | `ttl` _string_ | TTL is the TTL for the secret ID, after which it becomes invalid. | ...
```

The shape is what matters and it is deterministic: the gap note (written by
`generate.GAP_NOTE`, not by the model), then one ungrounded paragraph, then the closest
retrieved page with its excerpt, and no citation marker anywhere because no span exists.
The prose in the middle is the model's and must be captured from a live run; do not
script it.

Point at: this is what a gap looks like when the corpus is *nearly* right. The chunk is
about AppRole secret ID TTLs and scores 0.669 - high enough that a score threshold alone
would have let it through - so the answer is withheld as *grounded* text: there is no
claim, no marker, nothing to open. `generate.ungrounded_answer: assist` is what the demo
config sets, and it is the only surface that sets it (`ADR-0020`): the evaluation cells
all run `abstain`, where this panel ends after the note.

Without the policy the screen stops at the first line:

```
**The documentation provided does not contain an answer to this question.**

The best chunk scored 0.669, above the abstain threshold of -100.000, but the generator returned no claim it could support from it (The provided context does not state how an AppRole secret ID TTL determines the Vault Agent auto-auth token TTL. It shows secret ID TTL and token TTL as separate AppRole settings, but does not specify the resulting agent token TTL for a 30-minute secret ID.).
```

Note the grade on the last line: `abstain_score_threshold` is `-100.0` in this
configuration, i.e. score-based abstention is switched off and the generator is the
only gate (`ADR-0011`). With a score threshold in force the explanation line reads
differently ("below this configuration's abstain threshold of X") and the same chunk
is still shown.

## What this demo deliberately does not show

- No judge verdicts. The NLI and model judges (`ticket 10`) are a measurement layer,
  not a display layer; the demo stops at containment, which is the part that is
  arithmetic rather than opinion.
- No confidence number. Retrieval score is shown as a score, never as a probability
  that the answer is right.
- No multi-hop. `retrieval.hops` is 1 in the served configuration, so
  `hit_first_round` is the stop reason on all five questions; the footer would show
  the hop count if it were higher.

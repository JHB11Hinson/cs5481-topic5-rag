# Corpus: Vault 1.21.x documentation, pinned by commit

The knowledge base is the Vault documentation at `content/vault/v1.21.x` inside `hashicorp/web-unified-docs`, pinned by commit SHA recorded in the corpus manifest. Measured content: 1,586 files, 6.22 MB, ≈1.56 M tokens, ≈2,560 rendered pages.

The measurement killed the first choice. ClickHouse's English docs were picked on a guess of ~1.2 M tokens; they measure 8.02 M across 2,777 files, six times the estimate, because the docs tree also carries nine locale duplicates and a built `_site`. PostgreSQL 17 (`REL_17_STABLE`, 386 files, 3.10 M tokens) is the most stable pinnable source measured and was the runner-up, but it is twice the intended size and arrives as DocBook SGML, which buys parsing work with no payoff on a project that already has enough of it. Airflow (0.79 M core), Prometheus (0.15 M), scikit-learn (0.69 M), and nginx (0.09 M) are below the band. Kubernetes is 4.05 M only because `reference/` is generated API documentation that triples the prose volume.

Vault sits at 1.56 M tokens — comfortably above trivial, half of PostgreSQL, and inside the 1.5–5 M band the experiment design can chew through. It also gives this project a better argument than a database manual: secrets management is a domain where a confidently wrong answer is expensive, which is precisely the case for programmatic citation verification and a calibrated refusal path. And because the OSS documentation is interleaved with Enterprise-only features, near-miss golden items arise naturally instead of being invented.

Considered and kept as fallbacks: Grafana `docs/sources` (1.93 M, tag-pinnable, plain markdown) and Kubernetes prose-only (1.26 M, `reference/` dropped).

## Consequences

The repo is a Next.js site repository, so a full clone drags thousands of images; ingest uses a blobless sparse checkout of the one content directory and never materialises the rest. Pages are MDX, so the structure-aware parser has to strip React components while preserving headings, tables, and fenced code — which gives the parse comparison real content instead of a formality. The documentation drifts on `main`, so the pin must be a commit SHA, not a branch name.

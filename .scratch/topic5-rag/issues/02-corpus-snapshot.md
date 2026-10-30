# 02: Real corpus at a pinned snapshot, two parse variants

**What to build:** the same smoke command pointed at the real documentation repository produces a corpus snapshot identified by ref and commit, with a manifest and two parse variants — structure-aware (headings, pipe tables, fenced code preserved) and stripped plain text. Re-running the same ref reproduces identical content hashes; a different ref produces a different snapshot id and leaves the old one untouched.

**Blocked by:** 01.

**Status:** done

Corpus locked by `ADR-0008`: Vault 1.21.x documentation, path `content/vault/v1.21.x` plus `global` inside `hashicorp/web-unified-docs`, pinned at commit `1817bdfe`. Ingested with a blobless sparse checkout — the repo is a Next.js site and a full clone drags thousands of images. Pages are MDX; React components are stripped while headings, pipe tables, and fenced code survive. Shared include fragments follow `ADR-0009`.

Shipped: `ragqa/ingest.py`, `scripts/golden_probe.py`, snapshot `vault-1.21.x-1817bdfe`. 783 pages + 485 shared fragment documents = 1,268 documents, 5.62 M structured chars (≈1.41 M tokens), 0 parse failures, 33 unresolved include references (kept for a later look, not silently dropped).

- [x] `ragqa ingest` writes `manifest.json` with repo, ref, commit, fetch time, tool versions, and per-document doc_id, URL, path, size, content hash
- [x] `docs_structured.jsonl` and `docs_plain.jsonl` share doc_ids; tables and code fences survive in the structured variant and are gone from the plain one
- [x] Re-ingest of the same ref is byte-identical
- [x] Network access sits behind one function; the transform is pure and unit-tested on a table doc, a code-fence doc, and a deeply nested heading doc
- [x] Snapshot id recorded in every downstream artifact
- [x] Sparse checkout leaves the image tree on disk unvisited; the manifest records the file count actually read

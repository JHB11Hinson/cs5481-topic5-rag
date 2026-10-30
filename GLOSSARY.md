# Grounded Documentation QA

A question-answering system over a version-pinned set of product documentation. It answers only from retrieved passages and names the passage behind every claim, and says so when the documentation does not contain the answer.

## Language

### Corpus

**Knowledge Base**:
A version-pinned corpus plus the index built from it. Both halves move together; an index without its corpus snapshot is not a knowledge base.
_Avoid_: dataset, database, vector store

**Corpus Snapshot**:
The frozen set of source documents identified by a release tag or commit SHA. Every reported number is tied to exactly one snapshot.
_Avoid_: data dump, scrape

**Document**:
One addressable source file in the corpus, with a stable identifier and a canonical URL.
_Avoid_: page, article, file

**Chunk**:
A contiguous span of one document, the unit that gets embedded and retrieved.
_Avoid_: passage, snippet, fragment

**Chunk Strategy**:
The named rule that turns documents into chunks — its size, its overlap, and its boundary criterion. Stated as parameters, never as a vibe.
_Avoid_: splitting, segmentation, windowing

**Parent Chunk**:
The coarser chunk that a retrieved chunk belongs to and that gets handed to the generator instead of the retrieved one.
_Avoid_: big chunk, context block

**Contextual Prefix**:
A short generated sentence prepended to a chunk before embedding, situating that chunk inside its document.
_Avoid_: summary, metadata, enrichment

### Retrieval

**Retrieval Hit**:
A golden question whose evidence chunk appears in the returned top-k.
_Avoid_: match, success

**Hybrid Retrieval**:
Running a lexical scorer and a dense scorer over the same query and merging their ranked lists.
_Avoid_: combined search, mixed search

**Rerank**:
Rescoring a retrieved candidate list with a slower, more accurate model, without changing which candidates were retrieved.
_Avoid_: re-search, second retrieval

**Retrieval Depth**:
The k of top-k handed to the next stage. Distinguished from the number of chunks finally shown to the generator.
_Avoid_: limit, top-n

**Agentic Retrieval Loop**:
A bounded cycle in which the model decomposes or rewrites the question from what the previous round failed to find, then retrieves again. Bounded means a hard round cap and a recorded stop reason.
_Avoid_: agent, tool use, reasoning loop

### Grounding

**Grounded Answer**:
An answer every claim of which is supported by a retrieved chunk.
_Avoid_: faithful answer, cited answer

**Citation**:
A pointer from a claim to the Document and Chunk that supports it.
_Avoid_: reference, source link

**Span**:
A character range inside one chunk. Finer than a Citation, and the thing an automated checker can actually verify.
_Avoid_: offset, highlight region

**Citation Precision**:
The share of emitted citations that really do support the claim they are attached to.
_Avoid_: citation accuracy

**Abstention**:
The system's explicit statement that the knowledge base does not answer the question, produced instead of an answer.
_Avoid_: refusal, no-answer, fallback

**Faithfulness**:
The degree to which an answer's claims follow from its retrieved context, independent of whether the context was the right context.
_Avoid_: correctness, accuracy

### Evaluation

**Golden QA Set**:
The fixed question set with reference answers and reference evidence, split into answerable and deliberately unanswerable items.
_Avoid_: test set, benchmark, eval data

**Configuration**:
One point in the factorial grid — a specific chunk strategy, retrieval mode, and prefix setting. Numbers are always reported per configuration.
_Avoid_: variant, run, experiment

**Ablation**:
Removing or replacing one component and measuring what changes. The component is present or absent; nothing else moves.
_Avoid_: comparison, variant test

**Sensitivity Sweep**:
Varying one parameter across several values to get a curve rather than a single difference. Not an ablation — nothing is removed, the dial is turned.
_Avoid_: tuning, hyperparameter search

**Smoke Configuration**:
A deliberately tiny configuration (a handful of questions, one cell) run after every code change to prove the pipeline still executes end to end. Never cited in the report.
_Avoid_: quick test, sanity run

**Error Taxonomy**:
The fixed list of failure classes that every hand-inspected failure is assigned to.
_Avoid_: failure list, bug list

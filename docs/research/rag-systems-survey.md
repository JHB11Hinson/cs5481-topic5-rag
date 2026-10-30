# How mature RAG systems are actually built (module-level survey)

Verified 2026-10-30; `unverified` = no source found.

## A. Ingestion, chunking, retrieval, reranking

| System | Ingestion / parsing | Chunking | Retrieval | Reranking |
|---|---|---|---|---|
| **RAGFlow** | DeepDoc: layout analysis, OCR, table recognition, CPU inference ([README](https://github.com/infiniflow/ragflow)) | template-based ("explainable") per doc type; chunk visualization | "Multiple recall paired with fused re-ranking"; agentic multi-step retrieval, Low→Ultra depth ([README](https://github.com/infiniflow/ragflow)) | pluggable reranker registered next to LLM/embedder ([README](https://github.com/infiniflow/ragflow)) |
| **QAnything** | PaddleOCR + dedicated PDF parser with table handling; file preview | unverified | two-stage `bce-embedding-base_v1` → rerank; BM25+embedding hybrid in Docker build only ([README](https://github.com/netease-youdao/QAnything)) | `bce-reranker-base_v1`, default since v1.1.1 ([README](https://github.com/netease-youdao/QAnything)) |
| **Kotaemon** | selectable loaders: Azure DI, Adobe PDF Extract, Docling, PaddleOCR | unverified | hybrid full-text + vector; question decomposition; ReAct/ReWOO agents ([README](https://github.com/Cinnamon/kotaemon)) | reranking in default pipeline, model not named ([README](https://github.com/Cinnamon/kotaemon)) |
| **R2R** | multimodal ingest: txt/pdf/json/png/mp3 | unverified | hybrid semantic+keyword with **reciprocal rank fusion**; entity/relation graph; deep-research agent ([README](https://github.com/SciPhi-AI/R2R/blob/main/py/README.md)) | unverified |
| **Verba** (archived) | Unstructured, Firecrawl, Upstage Document Parse, AssemblyAI | token, sentence, semantic, recursive, HTML, Markdown, Code, JSON ([README](https://github.com/weaviate/Verba)) | hybrid semantic + keyword ([README](https://github.com/weaviate/Verba)) | "planned", never shipped ([README](https://github.com/weaviate/Verba)) |
| **AnythingLLM** | unverified | char window, 1000 chars default, small overlap ([docs](https://docs.anythingllm.com/setup/embedder-configuration/text-splitting)) | unverified | unverified |
| **Open WebUI** | 8 engines: Tika, Docling, Azure, Mistral OCR, Marker, MinerU, PaddleOCR, custom ([docs](https://docs.openwebui.com/features/)) | size/overlap, plus "full context mode" that skips chunking ([docs](https://docs.openwebui.com/features/)) | hybrid **BM25 + vector**; agentic retrieval via function calling ([docs](https://docs.openwebui.com/features/)) | **cross-encoder** reranker ([docs](https://docs.openwebui.com/features/)) |
| **Microsoft GraphRAG** | text units → LLM entity/relation extraction | token windows (defaults unverified) | local + global over Leiden community summaries, map-reduce partials ([paper](https://arxiv.org/abs/2404.16130)) | none |
| **LightRAG** | MinerU / Docling / native; native handles images, tables, formulas | four strategies: Fixed, Recursive, **Vector semantic**, **Paragraph semantic** (heading/table-aligned) ([README](https://github.com/HKUDS/LightRAG)) | KG dual-level: local / global / hybrid / naive / mix; LLM keyword extraction ([README](https://github.com/HKUDS/LightRAG)) | supported, on by default in `mix` mode ([README](https://github.com/HKUDS/LightRAG)) |
| **RAGatouille / ColBERT** | none (splits internally) | internal split | **late interaction**: ColBERTv2 + PLAID index ([README](https://github.com/AnswerDotAI/RAGatouille)) | the late-interaction scorer *is* the ranker |
| **Haystack** | converters (PyPDF, Docling, Unstructured) | `DocumentSplitter`: word/sentence/passage/page/line + overlap ([docs](https://docs.haystack.deepset.ai/docs/documentjoiner)) | BM25 + embedding retrievers; `DocumentJoiner`: weighted merge, **RRF**, distribution-based fusion; QueryExpander ([docs](https://docs.haystack.deepset.ai/docs/documentjoiner)) | rankers incl. LLM rankers |
| **LlamaIndex** | readers + LlamaParse | SentenceSplitter, TokenTextSplitter, SemanticSplitter, SentenceWindow+MetadataReplacement, Hierarchical+AutoMerging ([docs](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/)) | fusion/hybrid and recursive retrievers | reranker modules (Cohere, SentenceTransformer) |
| **Dify** | unverified (chunk settings + preview UI) ([docs](https://docs.dify.ai/en/cloud/use-dify/knowledge/create-knowledge/chunking-and-cleaning-text)) | separator + max length + overlap | hybrid vector+keyword, multi-path retrieval; index method High-Quality vs Economical ([docs](https://docs.dify.ai/en/cloud/use-dify/knowledge/create-knowledge/setting-indexing-methods)) | Cohere Rerank, bge-reranker, Jina ([blog](https://dify.ai/blog/hybrid-search-rerank-rag-improvement)) |

## B. Grounding, evaluation, other

| System | Citation / grounding | Built-in eval | Notable |
|---|---|---|---|
| RAGFlow | "Traceable citations" to key references; chunk-level visualization ([README](https://github.com/infiniflow/ragflow)) | unverified | Knowledge Compilation (Wiki/Graph/Tree/PageIndex); incremental sync ([README](https://github.com/infiniflow/ragflow)) |
| QAnything | File traceability preview ([README](https://github.com/netease-youdao/QAnything)) | model-level MTEB + LlamaIndex evals only ([README](https://github.com/netease-youdao/QAnything)) | cross-lingual, air-gapped install |
| Kotaemon | PDF viewer with highlighted spans + relevance score; **warns on low-relevance retrieval** ([README](https://github.com/Cinnamon/kotaemon)) | unverified | GraphRAG index (nano / LightRAG / MS); multi-user |
| R2R | `rag()` returns citations ([README](https://github.com/SciPhi-AI/R2R/blob/main/py/README.md)) | unverified | auth + collections (multi-tenant); deep-research agent |
| Verba | retrieved chunks shown, no verification ([README](https://github.com/weaviate/Verba)) | same, never shipped ([README](https://github.com/weaviate/Verba)) | single-user, 3D viewer |
| AnythingLLM | unverified | unverified | many vector DBs |
| Open WebUI | per-source citation list ([docs](https://docs.openwebui.com/features/)) | arenas / A-B / ELO leaderboards, **not** faithfulness ([docs](https://docs.openwebui.com/features/)) | 13 vector DBs |
| GraphRAG | answers derived from community summaries ([paper](https://arxiv.org/abs/2404.16130)) | LLM-judged comprehensiveness + diversity ([paper](https://arxiv.org/abs/2404.16130)) | maintenance mode ([README](https://github.com/microsoft/graphrag)) |
| LightRAG | citation + source attribution ([README](https://github.com/HKUDS/LightRAG)) | RAGAS + Langfuse; paper: comprehensiveness/diversity/empowerment ([README](https://github.com/HKUDS/LightRAG)) | incremental update, delete-with-KG-rebuild, 4 role-scoped LLMs |
| RAGatouille | n/a | none | trainable ColBERT, hard-negative mining, CPU-fast PLAID ([README](https://github.com/AnswerDotAI/RAGatouille)) |
| Haystack | no span alignment (unverified) | DocumentRecall/MRR/NDCG/MAP, Faithfulness, ContextRelevance, Ragas, DeepEval ([docs](https://docs.haystack.deepset.ai/docs/evaluators)) | DAG pipelines |
| LlamaIndex | CitationQueryEngine (detail unverified) | retriever + response evaluators ([docs](https://developers.llamaindex.ai/python/framework/module_guides/evaluating/)) | ingestion pipeline with docstore dedup |
| Dify | retrieval node returns scored chunks to the answer ([docs](https://docs.dify.ai/en/cloud/use-dify/knowledge/readme)) | unverified | workflow orchestration |

## 1. Table stakes vs differentiators

**Table stakes (implementing earns nothing):** dense embedding + vector DB; fixed/recursive chunking with overlap; one reranker as stage 2; top-k context stuffing; showing the source doc name; a chunk-size knob.

**Differentiators (2–3 systems only — score here):**
- Table-structure-aware parsing: DeepDoc (RAGFlow), PaddleOCR+tables (QAnything), engine zoo (Open WebUI).
- Parent-child / small-to-big: LlamaIndex's `SentenceWindowNodeParser`+MetadataReplacement and `HierarchicalNodeParser`+AutoMerging are the only shipped, documented pair ([docs](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/)).
- Context prepended into embedding *and* BM25 index ("contextual retrieval"): no surveyed OSS ships it; −49% top-20 failures, −67% with reranking ([Anthropic](https://www.anthropic.com/research/contextual-retrieval)).
- Late chunking (embed long text, chunk before pooling) ([Jina](https://arxiv.org/abs/2409.04701)) — nothing surveyed ships it.
- Graph index (GraphRAG, LightRAG, R2R) or multi-vector late interaction (RAGatouille).
- Citation verification / abstention: Kotaemon's low-relevance warning is the only explicit "insufficient evidence" path found.

## 2. Failure modes these systems engineer around

| Failure mode | Who engineers around it, how |
|---|---|
| Tables/figures destroyed by parsing | TSR in DeepDoc ([RAGFlow](https://github.com/infiniflow/ragflow)); table-aware PDF parser ([QAnything](https://github.com/netease-youdao/QAnything)); LightRAG targets "missing header rows when long tables are split" ([README](https://github.com/HKUDS/LightRAG)) |
| Chunk boundaries split the answer | overlap; sentence windows + auto-merge to parents ([LlamaIndex](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/)); heading-aligned boundaries (LightRAG) |
| Chunk lacks document context (pronouns, period, company) | contextual embeddings + contextual BM25 ([Anthropic](https://www.anthropic.com/research/contextual-retrieval)); headings injected at query time, `ENABLE_CONTENT_HEADINGS` ([LightRAG](https://github.com/HKUDS/LightRAG)) |
| Exact identifiers / error codes missed by dense vectors | BM25 branch of hybrid search, motivated by "Error code TS-999" ([Anthropic](https://www.anthropic.com/research/contextual-retrieval)); acronym/ID argument ([Dify](https://dify.ai/blog/hybrid-search-rerank-rag-improvement)) |
| Recall degrading as corpus grows | two-stage retrieve-then-rerank ([QAnything](https://github.com/netease-youdao/QAnything), [Dify](https://dify.ai/blog/hybrid-search-rerank-rag-improvement)) |
| Hallucinated citations | chunk traceable references (RAGFlow), PDF span highlight + score (Kotaemon) |
| Duplicate / near-duplicate docs | LightRAG `source_conflict_repair` demotes duplicates, "never picks a winner on its own" ([README](https://github.com/HKUDS/LightRAG)) |
| Extraction timeouts, reference floods | reference-block dropping + token budgets (LightRAG) |

## 3. Metrics actually used in RAG eval tools/papers

| Stage | Metric | Canonical source |
|---|---|---|
| Retrieval | Recall@k, MRR, nDCG@k, MAP; hit rate = any gold doc in top-k | Haystack evaluators ([docs](https://docs.haystack.deepset.ai/docs/evaluators)); BEIR nDCG@10 ([paper](https://arxiv.org/abs/2104.08663)) |
| Failure framing | 1 − recall@20 ("retrieval failure rate") | [Anthropic](https://www.anthropic.com/research/contextual-retrieval) |
| Retrieval, LLM-judged | context precision, context recall, noise sensitivity | [Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) |
| Grounding | faithfulness (claims supported by context), response relevancy | [Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) |
| Grounding, alt | context relevance, groundedness, answer relevance = "RAG triad" | [TruLens](https://www.trulens.org/getting_started/core_concepts/rag_triad/) |
| End-to-end, few labels | context relevance, answer faithfulness, answer relevance via LM judges + PPI | [ARES](https://arxiv.org/abs/2311.09476) |
| Pairwise quality | comprehensiveness, diversity, empowerment, directness (win rate) | [GraphRAG](https://arxiv.org/abs/2404.16130), [LightRAG](https://github.com/HKUDS/LightRAG) |
| Citations | citation precision / recall (cited span supports claim) | no surveyed OSS harness implements it — `unverified` beyond paper definitions |

Course-brief: hit rate ≈ Recall@k; correctness needs an LLM judge + the 20-question set.

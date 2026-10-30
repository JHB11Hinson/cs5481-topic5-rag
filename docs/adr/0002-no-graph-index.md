# No graph index, no late-interaction retrieval, no fine-tuning

The system stays on flat chunk retrieval: dense plus sparse, optionally reranked. Entity-graph augmentation (GraphRAG / LightRAG), ColBERT-style late interaction, and embedding fine-tuning are deliberately out of scope.

All three are real techniques with real gains, and all three cost more than the report can pay back. Graph construction needs an entity/relation extraction pass over every chunk plus a community-summarisation pass, and its payoff shows up only on cross-document multi-hop questions — a question type this corpus (a single product's reference manual) barely produces. Late interaction multiplies index size per token and complicates the storage story that the report has to justify. Fine-tuning needs labelled pairs the project does not have, and would make the chunking and retrieval ablations harder to attribute.

The point of cutting them is to spend the budget on measurement density instead: a factorial grid over chunking, retrieval mode, and contextual prefixes, each cell with citation precision, faithfulness, and abstention numbers. That is what a data-engineering grade rewards. Revisit if error analysis shows that a meaningful share of failures are genuinely multi-hop.

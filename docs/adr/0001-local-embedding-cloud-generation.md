# Local embedding and reranking, cloud generation

The project runs on a single RTX 3060 Laptop GPU with 6 GB VRAM. We embed the corpus and rerank candidates locally (bge-m3, bge-reranker-v2-m3) and call a hosted API only for answer generation and LLM-as-judge scoring.

The 6 GB budget is not a constraint on the encoding side: bge-m3 is 568 M parameters, 1.14 GB in fp16, and embeds a 6.1 M token corpus in roughly 6.5 minutes — so the full corpus can be re-embedded once per chunking strategy without thinking about money or time. The constraint lands on generation instead: a 7B Q4_K_M model takes 4.1–4.9 GB of weights, leaving about 1.2 GB of KV cache, which caps usable context at ~4 K tokens — six to eight chunks. That directly undermines the thing this project is graded on, since grounded answers with verifiable citations need a wider retrieved context than 4 K allows. Hosted generation also keeps the 20–40 configuration experiment sweep affordable: the whole sweep lands under ¥50.

Consequences worth knowing: the query path depends on the network, so an offline demo needs a fallback; and the judge model must be a different (stronger) model than the generator, or the faithfulness numbers become self-graded.

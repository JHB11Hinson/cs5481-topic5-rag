"""Time and memory probe for the late-chunking document path.

    python scripts/late_probe.py [documents]

Encodes the first N documents whole and reports wall clock, peak VRAM, and how
many chunks came out of each one. Run this before the full corpus: a single
8,192-token document is the largest forward pass this project asks a 6 GB card
to perform.
"""

from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

from ragqa import chunk as chunk_mod
from ragqa import embed
from ragqa.corpus import load_documents

CORPUS = "data/corpus/vault-1.21.x-1817bdfe/docs_structured.jsonl"


def main(argv):
    limit = int(argv[1]) if len(argv) > 1 else 5
    docs = load_documents(CORPUS)[:limit]
    late = embed.LateChunkingEmbedder(max_seq_length=8192)

    total_chunks = 0
    started = time.perf_counter()
    for doc in docs:
        children = [
            c for c in chunk_mod.chunk_recursive(doc, 512, 1024) if c["kind"] == "child"
        ]
        spans = [(c["char_start"], c["char_end"]) for c in children]
        began = time.perf_counter()
        vectors = late.encode_document(doc["text"], spans)
        elapsed = time.perf_counter() - began
        total_chunks += len(vectors)
        print(
            f"{doc['doc_id'][:52]:<52} chars={len(doc['text']):>6} chunks={len(vectors):>3} "
            f"{elapsed:>6.2f}s"
        )

    wall = time.perf_counter() - started
    import torch

    print(
        f"\n{len(docs)} documents, {total_chunks} chunks, {wall:.1f}s "
        f"({total_chunks / wall:.1f} chunks/s), peak VRAM "
        f"{torch.cuda.max_memory_allocated() / 1e9:.2f} GB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

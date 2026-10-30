# Late chunking runs over windows of 2,048 tokens, not whole documents

Documents are encoded in windows of 2,048 tokens with 256 tokens of overlap, and a chunk's vector is pooled from the token states that cover its span. A span crossing a window boundary is pooled from every window that covers part of it, weighted by the tokens each contributes.

The model's 8,192-token window is what makes late chunking possible at all, so the first implementation used it whole. The probe was decisive against that: five documents, 26 chunks, 47 seconds, **peak 5.56 GB of a 6.00 GB card**, and a 53 k-char document truncated at 8,192 tokens — meaning its later chunks were pooled from token states that had never seen them, which is the exact failure late chunking exists to prevent. Attention is quadratic in sequence length and the batch is one document, so the ceiling arrives at a document count, not at a chunk count.

2,048 tokens keeps four times the context of a 512-token chunk while leaving headroom on the card, and the overlap means a chunk near a boundary is pooled from a window that contains it in context rather than clipped at its first token.

## Consequences

The cache key includes the window geometry (`w2048-o256-s8192`), so changing the window is a new measurement rather than a silently different one under an old key. Every run reports the window count and how many documents needed more than one window, which is the number a reader needs to judge how much context a chunk really carried. Documents are still tokenised whole, so the offset mapping is document-global and spans never shift between windows.

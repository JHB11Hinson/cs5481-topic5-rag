"""Embedders and the embedding cache.

`StubEmbedder` is a deterministic hashed bag-of-words encoder: dependency-free,
and good enough that retrieval on the fixture corpus behaves like retrieval
rather than noise (ticket 01).

`BgeM3Embedder` is the real one (ticket 04): bge-m3 in fp16 on CUDA when
available, disk-cached by `(model, version, sha256(text))` so re-indexing costs
nothing. The 8,192-token window is what makes late chunking possible later
(ADR-0006), so it is set explicitly rather than left at the model default.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_TOKEN = re.compile(r"[a-z0-9_]+")


class StubEmbedder:
    provider = "stub"

    def __init__(self, dim: int = 256):
        if dim <= 0:
            raise ValueError("embed.dim must be positive")
        self.dim = int(dim)
        self.model_id = "stub-hashing"
        self.model_version = "1"
        self.last_stats: Dict[str, int] = {"hits": 0, "misses": 0}

    def _one(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float64)
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            vector[bucket] += 1.0
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        return vector

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self.last_stats = {"hits": 0, "misses": len(texts)}
        return [self._one(text).tolist() for text in texts]


class EmbeddingCache:
    """SQLite keyed by (model, version, sha256(text)) → float32 vector."""

    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        # Built in the main thread, read from Chainlit's worker threads: the check has
        # to come off, and every statement has to be serialised behind a lock.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            " key TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def key(model: str, version: str, salt: str, text: str) -> str:
        return hashlib.sha256(
            f"{model}|{version}|{salt}|{text}".encode("utf-8")
        ).hexdigest()

    def get(self, key: str) -> Optional[np.ndarray]:
        with self._lock:
            row = self._conn.execute(
                "SELECT dim, vector FROM embeddings WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            dim, blob = row
            return np.frombuffer(blob, dtype=np.float32).astype(np.float64).reshape(dim)

    def put(self, key: str, vector: np.ndarray) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO embeddings (key, dim, vector) VALUES (?, ?, ?)",
                (key, int(vector.shape[0]), vector.astype(np.float32).tobytes()),
            )

    def flush(self) -> None:
        with self._lock:
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self.flush()
            self._conn.close()


class BgeM3Embedder:
    provider = "bge-m3"

    def __init__(
        self,
        model_id: str = "BAAI/bge-m3",
        device: str = "auto",
        batch_size: int = 16,
        max_seq_length: int = 8192,
        cache_path: str = "data/cache/embeddings.sqlite",
        model_version: str = "local",
    ):
        from sentence_transformers import SentenceTransformer  # imported lazily

        self.model_id = model_id
        self.model_version = model_version
        self.batch_size = int(batch_size)
        self.max_seq_length = int(max_seq_length)
        self.cache = EmbeddingCache(cache_path)
        self.model = SentenceTransformer(model_id, device=None if device == "auto" else device)
        self.model.max_seq_length = self.max_seq_length
        try:
            self.model.half()
        except Exception:  # noqa: BLE001 - CPU builds have nothing to halve
            pass
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.last_stats: Dict[str, int] = {"hits": 0, "misses": 0}

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        keys = [
            EmbeddingCache.key(self.model_id, self.model_version, "chunk", text)
            for text in texts
        ]
        out: List[Optional[np.ndarray]] = [None] * len(texts)
        misses: List[int] = []
        for index, key in enumerate(keys):
            cached = self.cache.get(key)
            if cached is None:
                misses.append(index)
            else:
                out[index] = cached

        if misses:
            batch = [texts[index] for index in misses]
            vectors = self.model.encode(
                batch,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            for position, index in enumerate(misses):
                vector = np.asarray(vectors[position], dtype=np.float64)
                out[index] = vector
                self.cache.put(keys[index], vector)
            self.cache.flush()

        self.last_stats = {"hits": len(texts) - len(misses), "misses": len(misses)}
        return [vector.tolist() for vector in out if vector is not None]

    def close(self) -> None:
        self.cache.close()


class LateChunkingEmbedder:
    """Whole-document encoding, per-chunk pooling (ticket 09, ADR-0006).

    bge-m3 accepts 8,192 tokens, so a document can be encoded in one forward pass
    and each chunk's vector is the mean of the token states covering its character
    span. The chunk therefore carries its document's context without a generated
    prefix. Output is cached in its own namespace: the key includes the document
    hash, the span, and the window geometry, so it can never collide with
    chunk-level entries or with a run at a different window size.

    Windowing exists because the whole document does not fit on a 6 GB card:
    probing five documents at 8,192 tokens peaked at 5.56 GB of 6.00, and one
    53 k-char document truncated, so its later chunks were pooled from states that
    never saw them. Documents are therefore encoded in windows of
    `window_tokens` with `window_overlap` tokens of overlap; a span that crosses a
    boundary is pooled from every window that covers part of it, weighted by the
    number of tokens each window contributes. Every window is still several times
    the context of a 512-token chunk, which is the point of the mechanism.
    """

    provider = "bge-m3-late"

    def __init__(
        self,
        model_id: str = "BAAI/bge-m3",
        device: str = "cuda",
        max_seq_length: int = 8192,
        window_tokens: int = 2048,
        window_overlap: int = 256,
        cache_path: str = "data/cache/embeddings.sqlite",
        model_version: str = "local",
    ):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.model_version = model_version
        self.max_seq_length = int(max_seq_length)
        self.window_tokens = int(window_tokens)
        self.window_overlap = int(window_overlap)
        self.device = device if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(
            model_id, torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
        ).to(self.device)
        self.model.eval()
        self.cache = EmbeddingCache(cache_path)
        self._special_prefix = len(
            self.tokenizer.build_inputs_with_special_tokens([0])
        ) - 1
        self.last_stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "documents": 0,
            "windows": 0,
            "documents_over_window": 0,
            "peak_vram_bytes": 0,
        }

    def windows_for(self, token_count: int) -> List[Tuple[int, int]]:
        """Half-open token windows covering a document, overlapping at the seams."""
        size = max(1, min(self.window_tokens, self.max_seq_length))
        overlap = max(0, min(self.window_overlap, size // 2))
        stride = max(1, size - overlap)
        windows: List[Tuple[int, int]] = []
        start = 0
        while start < token_count:
            end = min(start + size, token_count)
            windows.append((start, end))
            if end >= token_count:
                break
            start += stride
        return windows or [(0, 0)]

    def _encode_window(self, token_ids: List[int]):
        torch = self.torch
        ids = self.tokenizer.build_inputs_with_special_tokens(token_ids)
        tensor = torch.tensor([ids], dtype=torch.long, device=self.device)
        attention = torch.ones_like(tensor)
        with torch.inference_mode():
            states = self.model(input_ids=tensor, attention_mask=attention).last_hidden_state[0]
        if self.device == "cuda":
            peak = int(torch.cuda.max_memory_allocated())
            self.last_stats["peak_vram_bytes"] = max(self.last_stats["peak_vram_bytes"], peak)
        self.last_stats["windows"] += 1
        return states

    def encode_document(self, text: str, spans: List[Tuple[int, int]]) -> List[List[float]]:
        """Vector per (start, end) character span, pooled from the document's states."""
        encoded = self.tokenizer(
            text,
            truncation=False,
            return_offsets_mapping=True,
            add_special_tokens=False,
        )
        offsets = [tuple(pair) for pair in encoded["offset_mapping"]]
        token_ids = encoded["input_ids"]

        doc_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        geometry = f"w{self.window_tokens}-o{self.window_overlap}-s{self.max_seq_length}"
        keys = [
            EmbeddingCache.key(
                self.model_id, self.model_version, f"{doc_key}:{start}:{end}:{geometry}", text
            )
            for start, end in spans
        ]

        out: List[Optional[np.ndarray]] = [None] * len(spans)
        pending: List[int] = []
        for index, key in enumerate(keys):
            cached = self.cache.get(key)
            if cached is None:
                pending.append(index)
            else:
                out[index] = cached
                self.last_stats["hits"] += 1

        if pending:
            windows = self.windows_for(len(offsets))
            if len(windows) > 1:
                self.last_stats["documents_over_window"] = (
                    self.last_stats.get("documents_over_window", 0) + 1
                )
            states_by_window: Dict[Tuple[int, int], Any] = {}

            def states_for(window: Tuple[int, int]):
                if window not in states_by_window:
                    states_by_window[window] = self._encode_window(
                        token_ids[window[0]:window[1]]
                    )
                return states_by_window[window]

            # One ordered sweep per window: advance a cursor across the document's
            # tokens once, so pooling stays linear rather than spans × window.
            ordered = sorted(pending, key=lambda i: spans[i][0])
            pooled: Dict[int, Tuple[Any, int]] = {}
            for window in windows:
                window_start, window_end = window
                cursor = window_start
                for index in ordered:
                    start, end = spans[index]
                    while cursor < window_end and offsets[cursor][1] <= start:
                        cursor += 1
                    first = -1
                    last = -1
                    probe = cursor
                    while probe < window_end and offsets[probe][0] < end:
                        if offsets[probe][1] > start:
                            if first < 0:
                                first = probe
                            last = probe + 1
                        probe += 1
                    if first < 0 or last <= first:
                        continue
                    states = states_for(window)
                    local_start = first - window_start + self._special_prefix
                    local_end = last - window_start + self._special_prefix
                    weight = local_end - local_start
                    block = states[local_start:local_end].mean(dim=0).float().cpu().numpy()
                    previous = pooled.get(index)
                    pooled[index] = (
                        block * weight if previous is None else previous[0] + block * weight,
                        weight if previous is None else previous[1] + weight,
                    )

            for index in pending:
                entry = pooled.get(index)
                if entry is None or entry[1] == 0:
                    # A span with no token overlap (whitespace only): the first token
                    # state is the least wrong answer and keeps the shape valid.
                    states = states_for(windows[0])
                    vector = (
                        states[self._special_prefix].float().cpu().numpy().astype(np.float64)
                    )
                else:
                    vector = (entry[0] / entry[1]).astype(np.float64)
                norm = float(np.linalg.norm(vector))
                if norm > 0:
                    vector = vector / norm
                out[index] = vector
                self.cache.put(keys[index], vector)
                self.last_stats["misses"] += 1
            self.cache.flush()

        self.last_stats["documents"] += 1
        return [vector.tolist() for vector in out if vector is not None]

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Not this class's job — and a loud reminder of why.

        A late-chunked index holds vectors pooled from document token spans; a query
        has no document span, so it must go through the ordinary sentence encoder or
        the contextualization levels would be compared against queries embedded in
        different spaces. `run.py` builds a second encoder for that (`query_embedder`).
        This method exists so that reaching for `embed` here fails with a sentence a
        reader can act on, instead of `AttributeError: no attribute 'embed'` — which
        cost six matrix cells one evening.
        """
        raise NotImplementedError(
            "LateChunkingEmbedder pools vectors from document spans and cannot embed a "
            "query; build a chunk-level embedder for queries (see ragqa/run.py, "
            "`query_embedder`)."
        )

    def close(self) -> None:
        self.cache.close()



def make(cfg) -> object:
    provider = cfg["embed.provider"]
    if provider == "stub":
        return StubEmbedder(dim=int(cfg["embed.dim"]))
    if provider == "bge-m3":
        return BgeM3Embedder(
            model_id=cfg["embed.model_id"] if cfg["embed.model_id"] != "stub-hashing" else "BAAI/bge-m3",
            device=cfg["embed.device"],
            batch_size=int(cfg["embed.batch_size"]),
            max_seq_length=int(cfg["embed.max_seq_length"]),
            cache_path=cfg["embed.cache_path"],
        )
    raise ValueError(f"unknown embed.provider {provider!r}")

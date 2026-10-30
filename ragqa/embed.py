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
        self._conn = sqlite3.connect(path)
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
        row = self._conn.execute(
            "SELECT dim, vector FROM embeddings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        dim, blob = row
        return np.frombuffer(blob, dtype=np.float32).astype(np.float64).reshape(dim)

    def put(self, key: str, vector: np.ndarray) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, dim, vector) VALUES (?, ?, ?)",
            (key, int(vector.shape[0]), vector.astype(np.float32).tobytes()),
        )

    def flush(self) -> None:
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

    def close(self) -> None:
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

    bge-m3 accepts 8,192 tokens, so a document fits in one forward pass and each
    chunk's vector is the mean of the token states covering its character span.
    The chunk therefore carries its document's context without a generated
    prefix. Output is cached in its own namespace: the key includes the document
    hash and the span, so it can never collide with chunk-level entries.
    """

    provider = "bge-m3-late"

    def __init__(
        self,
        model_id: str = "BAAI/bge-m3",
        device: str = "cuda",
        max_seq_length: int = 8192,
        cache_path: str = "data/cache/embeddings.sqlite",
        model_version: str = "local",
    ):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.model_version = model_version
        self.max_seq_length = int(max_seq_length)
        self.device = device if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(
            model_id, torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
        ).to(self.device)
        self.model.eval()
        self.cache = EmbeddingCache(cache_path)
        self.last_stats: Dict[str, int] = {"hits": 0, "misses": 0, "documents": 0, "windows": 0}

    def encode_document(self, text: str, spans: List[Tuple[int, int]]) -> List[List[float]]:
        """Vector per (start, end) span, pooled from the document's token states."""
        torch = self.torch
        encoded = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_seq_length,
            return_offsets_mapping=True,
        )
        offsets = encoded.pop("offset_mapping")[0].tolist()
        inputs = {key: value.to(self.device) for key, value in encoded.items()}

        with torch.inference_mode():
            states = self.model(**inputs).last_hidden_state[0]

        out: List[List[float]] = []
        doc_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for start, end in spans:
            key = EmbeddingCache.key(self.model_id, self.model_version, f"{doc_key}:{start}:{end}", text)
            cached = self.cache.get(key)
            if cached is not None:
                self.last_stats["hits"] += 1
                out.append(cached.tolist())
                continue
            indices = [
                index
                for index, (token_start, token_end) in enumerate(offsets)
                if token_end > start and token_start < end and token_end > token_start
            ]
            if not indices:
                indices = [0]
            vector = states[indices].mean(dim=0).float().cpu().numpy().astype(np.float64)
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm
            self.cache.put(key, vector)
            self.last_stats["misses"] += 1
            out.append(vector.tolist())
        self.last_stats["documents"] += 1
        self.cache.flush()
        return out

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

"""Vector indexes.

`MemoryIndex` serves the stub path. `QdrantIndex` is the real store (ticket 05).
Docker is unavailable on this machine, so it runs in Qdrant's embedded local
mode: same client API and same on-disk footprint to measure, no server process
to babysit. Point ids are uuid5 of the chunk id so a rebuild is idempotent.
"""

from __future__ import annotations

import os
import uuid
from typing import Dict, List, Sequence, Tuple

import numpy as np

NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, chunk_id))


class MemoryIndex:
    backend = "memory"

    def __init__(self) -> None:
        self._ids: List[str] = []
        self._matrix: np.ndarray = np.zeros((0, 0), dtype=np.float64)
        self.build_seconds = 0.0

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must be the same length")
        self._ids = list(ids)
        matrix = np.asarray(vectors, dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms

    def search(self, vector: Sequence[float], k: int) -> List[Tuple[str, float]]:
        if not self._ids:
            return []
        query = np.asarray(vector, dtype=np.float64)
        norm = float(np.linalg.norm(query))
        if norm == 0:
            return []
        scores = self._matrix @ (query / norm)
        order = np.argsort(-scores)[: max(1, k)]
        return [(self._ids[i], float(scores[i])) for i in order]

    def size_bytes(self) -> int:
        return int(self._matrix.nbytes)

    def count(self) -> int:
        return len(self._ids)

    def close(self) -> None:
        return None


class QdrantIndex:
    backend = "qdrant"

    def __init__(self, path: str, collection: str):
        from qdrant_client import QdrantClient

        self.path = path
        self.collection = collection
        os.makedirs(path, exist_ok=True)
        self.client = QdrantClient(path=path)
        self.dim = 0
        self.build_seconds = 0.0

    def _ensure_collection(self, dim: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection in existing:
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self.dim = dim

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        from qdrant_client.models import PointStruct

        if not ids:
            return
        self._ensure_collection(len(vectors[0]))
        points = [
            PointStruct(id=point_id(chunk_id), vector=list(vector), payload={"chunk_id": chunk_id})
            for chunk_id, vector in zip(ids, vectors)
        ]
        batch = 256
        for start in range(0, len(points), batch):
            self.client.upsert(collection_name=self.collection, points=points[start:start + batch])

    def search(self, vector: Sequence[float], k: int) -> List[Tuple[str, float]]:
        from qdrant_client.models import QueryResponse  # noqa: F401 - API probe

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection, query=list(vector), limit=max(1, k)
            )
            points = response.points
        else:  # pragma: no cover - older clients
            points = self.client.search(
                collection_name=self.collection, query_vector=list(vector), limit=max(1, k)
            )
        return [(hit.payload["chunk_id"], float(hit.score)) for hit in points]

    def size_bytes(self) -> int:
        total = 0
        for current, _, files in os.walk(self.path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(current, name))
                except OSError:
                    pass
        return total

    def count(self) -> int:
        try:
            return int(self.client.count(self.collection).count)
        except Exception:  # noqa: BLE001 - collection may not exist yet
            return 0

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass


def make(cfg, collection: str = "") -> object:
    backend = cfg["index.backend"]
    if backend == "memory":
        return MemoryIndex()
    if backend == "qdrant":
        name = collection or "chunks"
        return QdrantIndex(os.path.join(cfg["index.path"], name), name)
    raise ValueError(f"unknown index.backend {backend!r}")

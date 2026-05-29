from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

_HAS_CHROMADB: bool = False
try:
    import chromadb

    _HAS_CHROMADB = True
except ImportError:
    pass


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class _MemoryIndex:
    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._vectors[id] = vector
        self._metadata[id] = metadata

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for vid, vec in self._vectors.items():
            score = _cosine_similarity(query_vector, vec)
            scored.append((vid, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def check_similarity(
        self,
        vector: list[float],
        threshold: float,
    ) -> tuple[str, float] | None:
        best_id: str | None = None
        best_score: float = -1.0
        for vid, vec in self._vectors.items():
            score = _cosine_similarity(vector, vec)
            if score > best_score:
                best_score = score
                best_id = vid
        if best_id is not None and best_score >= threshold:
            return (best_id, best_score)
        return None

    def remove(self, id: str) -> None:
        self._vectors.pop(id, None)
        self._metadata.pop(id, None)

    def clear(self) -> None:
        self._vectors.clear()
        self._metadata.clear()

    def __len__(self) -> int:
        return len(self._vectors)


class _ChromaIndex:
    def __init__(self, persist_dir: str = "data/chroma") -> None:
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="beliefs",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._collection.add(
            ids=[id],
            embeddings=[vector],
            metadatas=[metadata],
        )

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]:
        result = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
        )
        ids: list[str] = result.get("ids", [[]])[0]
        distances: list[float] = result.get("distances", [[]])[0]
        if not ids:
            return []
        scores = [1.0 - d for d in distances]
        return list(zip(ids, scores))

    def check_similarity(
        self,
        vector: list[float],
        threshold: float,
    ) -> tuple[str, float] | None:
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=1,
        )
        ids: list[str] = result.get("ids", [[]])[0]
        distances: list[float] = result.get("distances", [[]])[0]
        if not ids:
            return None
        score = 1.0 - distances[0]
        if score >= threshold:
            return (ids[0], score)
        return None

    def remove(self, id: str) -> None:
        self._collection.delete(ids=[id])

    def clear(self) -> None:
        self._client.delete_collection("beliefs")
        self._collection = self._client.get_or_create_collection(
            name="beliefs",
            metadata={"hnsw:space": "cosine"},
        )

    def __len__(self) -> int:
        return self._collection.count()


class VectorStore:
    def __init__(self, persist_dir: str = "data/chroma") -> None:
        if _HAS_CHROMADB:
            logger.info("using_chromadb_persistent_index persist_dir=%s", persist_dir)
            self._index: _MemoryIndex | _ChromaIndex = _ChromaIndex(persist_dir)
        else:
            logger.info("using_in_memory_index (chromadb not available)")
            self._index = _MemoryIndex()

    async def add(
        self,
        id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._index.add(id, vector, metadata or {})

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        return self._index.search(query_vector, top_k)

    async def check_similarity(
        self,
        vector: list[float],
        threshold: float = 0.95,
    ) -> tuple[str, float] | None:
        return self._index.check_similarity(vector, threshold)

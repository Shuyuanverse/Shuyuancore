# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import IMemoryStore
from src.memory.base import MemoryEntry, MemoryStats
from src.memory.belief_store import PersistentBeliefStore
from src.memory.embedding import EmbeddingService
from src.memory.long_term import LongTermMemory
from src.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryStore(IMemoryStore):
    def __init__(
        self,
        long_term: LongTermMemory | None = None,
        vector_store: VectorStore | None = None,
        belief_store: PersistentBeliefStore | None = None,
    ) -> None:
        self._long_term: LongTermMemory | None = long_term
        self._vector_store: VectorStore | None = vector_store
        self._belief_store: PersistentBeliefStore | None = belief_store

    @property
    def long_term(self) -> LongTermMemory | None:
        return self._long_term

    @property
    def vector_store(self) -> VectorStore | None:
        return self._vector_store

    @property
    def belief_store(self) -> PersistentBeliefStore | None:
        return self._belief_store

    async def search(
        self,
        query: str,
        layers: list[int] | None = None,
    ) -> dict[int, list[MemoryEntry]]:
        result: dict[int, list[MemoryEntry]] = {}

        if self._long_term is not None:
            results = await self._long_term.retrieve_similar(query, top_k=20)
            for entry, score in results:
                if layers is None or entry.layer in layers:
                    result.setdefault(entry.layer, []).append(entry)

        for layer, entries in result.items():
            entries.sort(key=lambda e: e.confidence, reverse=True)

        return result

    async def store(self, entry: MemoryEntry, layer: int | None = None) -> str:
        target_layer = layer if layer is not None else entry.layer

        entry_data = MemoryEntry(
            id=entry.id,
            content=entry.content,
            memory_type=entry.memory_type,
            layer=target_layer,
            confidence=entry.confidence,
            created_at=entry.created_at,
            last_accessed=entry.last_accessed,
            metadata=entry.metadata,
        )

        if self._long_term is not None:
            return await self._long_term.store_entry(entry_data)

        logger.warning("No long-term memory backend available, entry not stored")
        return entry_data.id

    async def get_statistics(self) -> MemoryStats:
        if self._long_term is not None:
            return await self._long_term.get_statistics()

        return MemoryStats()


def get_memory_store(
    db_path: str = "data/state.db",
    chroma_path: str = "data/chroma",
    embedding_service: EmbeddingService | None = None,
) -> MemoryStore:
    vector_store: VectorStore | None = None
    if embedding_service is not None:
        vector_store = VectorStore(persist_dir=chroma_path)

    belief_store = PersistentBeliefStore(
        db_path=db_path,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    long_term = LongTermMemory(
        db_path=db_path,
        embedding_service=embedding_service,
    )

    return MemoryStore(
        long_term=long_term,
        vector_store=vector_store,
        belief_store=belief_store,
    )
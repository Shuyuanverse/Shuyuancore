from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import IMemoryStore
from src.memory.belief_store import PersistentBeliefStore
from src.memory.core_memory import CoreMemory
from src.memory.embedding import EmbeddingService
from src.memory.long_term import LongTermMemory
from src.memory.persona_memory import PersonaMemory
from src.memory.relational import RelationalMemory
from src.memory.vector_store import VectorStore
from src.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryStore(IMemoryStore):
    def __init__(
        self,
        db_path: str = "data/state.db",
        chroma_path: str = "data/chroma",
        embedding_service: EmbeddingService | None = None,
        user_id: str = "anonymous",
    ) -> None:
        self._db_path = db_path
        self._chroma_path = chroma_path
        self._user_id = user_id
        self._embedding_service = embedding_service
        self._vector_store: VectorStore | None = None
        self._belief_store: PersistentBeliefStore | None = None
        self._core_memory: CoreMemory | None = None
        self._working_memory: WorkingMemory | None = None
        self._long_term: LongTermMemory | None = None
        self._relational: RelationalMemory | None = None
        self._persona: PersonaMemory | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()

        self._vector_store = VectorStore(persist_dir=self._chroma_path)

        self._belief_store = PersistentBeliefStore(
            db_path=self._db_path,
            embedding_service=self._embedding_service,
            vector_store=self._vector_store,
        )

        self._core_memory = CoreMemory()
        await self._core_memory.load()

        self._working_memory = WorkingMemory(
            db_path=self._db_path,
            user_id=self._user_id,
        )
        await self._working_memory.initialize()

        self._long_term = LongTermMemory(
            belief_store=self._belief_store,
            embedding_service=self._embedding_service,
            vector_store=self._vector_store,
        )

        self._relational = RelationalMemory(db_path=self._db_path)

        self._persona = PersonaMemory()

        self._initialized = True
        logger.info(
            "MemoryStore initialized: db=%s chroma=%s user=%s",
            self._db_path,
            self._chroma_path,
            self._user_id,
        )

    @property
    def belief_store(self) -> PersistentBeliefStore:
        if not self._initialized or self._belief_store is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._belief_store

    @property
    def core_memory(self) -> CoreMemory:
        if not self._initialized or self._core_memory is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._core_memory

    @property
    def working_memory(self) -> WorkingMemory:
        if not self._initialized or self._working_memory is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._working_memory

    @property
    def long_term(self) -> LongTermMemory:
        if not self._initialized or self._long_term is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._long_term

    @property
    def relational(self) -> RelationalMemory:
        if not self._initialized or self._relational is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._relational

    @property
    def persona(self) -> PersonaMemory:
        if not self._initialized or self._persona is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._persona

    @property
    def vector_store(self) -> VectorStore:
        if not self._initialized or self._vector_store is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._vector_store

    @property
    def embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            raise RuntimeError("MemoryStore has no embedding service configured.")
        return self._embedding_service

    async def search(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[Any]:
        if not self._initialized:
            return []
        return await self._belief_store.search_similar(query, top_k, min_confidence)

    async def get_statistics(self) -> dict[str, Any]:
        if not self._initialized:
            return {"initialized": False}

        stats: dict[str, Any] = {
            "initialized": True,
            "layers": {},
        }

        try:
            stats["layers"]["working_memory"] = {
                "projects": len(self._working_memory._projects),
            }
        except Exception:
            pass

        try:
            lt_stats = await self._long_term.get_statistics()
            stats["layers"]["long_term"] = lt_stats
        except Exception:
            stats["layers"]["long_term"] = {"error": "unavailable"}

        stats["layers"]["relational"] = self._relational.get_summary()

        return stats

    async def close(self) -> None:
        if self._belief_store is not None:
            await self._belief_store.close()
        if self._working_memory is not None:
            await self._working_memory.close()

        self._initialized = False
        logger.info("MemoryStore closed")

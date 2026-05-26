from __future__ import annotations

import time
import uuid
from typing import Any

from src.core.interfaces import Belief, IBeliefStore


class BeliefStore(IBeliefStore):

    def __init__(self) -> None:
        self._store: dict[str, list[Belief]] = {}
        self._by_id: dict[str, Belief] = {}

    async def add(self, conversation_id: str, belief: Belief) -> str:
        if conversation_id not in self._store:
            self._store[conversation_id] = []
        self._store[conversation_id].append(belief)
        self._by_id[belief.id] = belief
        return belief.id

    async def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        beliefs = self._store.get(conversation_id, [])
        return beliefs[-limit:]

    async def get_by_id(self, belief_id: str) -> Belief | None:
        return self._by_id.get(belief_id)

    async def update(self, belief: Belief) -> None:
        self._by_id[belief.id] = belief

    async def clear(self, conversation_id: str) -> None:
        beliefs = self._store.pop(conversation_id, [])
        for b in beliefs:
            self._by_id.pop(b.id, None)

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        beliefs = self._store.get(conversation_id)
        if beliefs is None:
            return
        self._store[conversation_id] = [
            b for b in beliefs if b.id != belief_id
        ]
        self._by_id.pop(belief_id, None)

    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]:
        return []

    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None:
        pass

    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        pass
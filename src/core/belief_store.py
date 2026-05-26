from __future__ import annotations

import time
import uuid
from typing import Any

from src.core.interfaces import Belief, IBeliefStore


class BeliefStore(IBeliefStore):

    def __init__(self) -> None:
        self._store: dict[str, list[Belief]] = {}

    def add(self, conversation_id: str, belief: Belief) -> None:
        if conversation_id not in self._store:
            self._store[conversation_id] = []
        self._store[conversation_id].append(belief)

    def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        beliefs = self._store.get(conversation_id, [])
        return beliefs[-limit:]

    def clear(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)

    def remove(self, conversation_id: str, belief_id: str) -> None:
        beliefs = self._store.get(conversation_id)
        if beliefs is None:
            return
        self._store[conversation_id] = [
            b for b in beliefs if b.id != belief_id
        ]

    @staticmethod
    def create_belief(
        content: str,
        source: str,
        confidence: float = 1.0,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Belief:
        return Belief(
            id=str(uuid.uuid4()),
            content=content,
            source=source,
            confidence=confidence,
            timestamp=int(time.time() * 1000),
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

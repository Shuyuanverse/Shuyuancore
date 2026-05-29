from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import Belief, IBeliefStore, IReader

logger = logging.getLogger(__name__)

_MEMORY_TYPE_ROLE_MAP: dict[str, str] = {
    "identity": "system",
    "preference": "system",
    "task": "system",
    "agreement": "system",
    "fact": "system",
    "emotion": "system",
    "chat": "assistant",
}


class BeliefReader(IReader):
    def __init__(self, belief_store: IBeliefStore) -> None:
        self._belief_store = belief_store

    async def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        all_beliefs = await self._belief_store.get(conversation_id, limit=200)

        l1_beliefs: list[Belief] = []
        l2_beliefs: list[Belief] = []
        l3_plus_beliefs: list[Belief] = []

        for belief in all_beliefs:
            if belief.layer == 1:
                l1_beliefs.append(belief)
            elif belief.layer == 2:
                l2_beliefs.append(belief)
            else:
                l3_plus_beliefs.append(belief)

        similar_beliefs: list[tuple[Belief, float]] = []
        if user_query:
            similar_beliefs = await self._belief_store.search_similar(
                user_query, top_k=5, min_confidence=0.1
            )

        seen_ids: set[str] = set()
        scored_beliefs: list[tuple[Belief, float]] = []

        for belief in l1_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 1.0
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        for belief in l2_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 0.9
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        if similar_beliefs:
            for belief, relevance in similar_beliefs:
                if belief.id not in seen_ids:
                    score = belief.confidence * relevance
                    scored_beliefs.append((belief, score))
                    seen_ids.add(belief.id)

        for belief in l3_plus_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 0.5
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        scored_beliefs.sort(key=lambda x: x[1], reverse=True)

        messages: list[dict[str, Any]] = []
        current_tokens = 0

        for belief, _score in scored_beliefs:
            role = _MEMORY_TYPE_ROLE_MAP.get(belief.memory_type, "system")
            prefix = _layer_prefix(belief.layer, belief.memory_type)

            content = f"{prefix}: {belief.content}"
            estimated_tokens = max(1, len(content) // 4)

            if current_tokens + estimated_tokens > max_tokens:
                continue

            messages.append({"role": role, "content": content})
            current_tokens += estimated_tokens

        logger.debug(
            "BeliefReader: read %d beliefs (%d tokens) for conversation %s",
            len(scored_beliefs),
            current_tokens,
            conversation_id,
        )

        return messages


def _layer_prefix(layer: int, memory_type: str) -> str:
    layer_labels: dict[int, str] = {
        1: "[Core Memory]",
        2: "[Working Memory]",
        3: "[Long-term]",
        4: "[Skill]",
        5: "[Relational]",
        6: "[Persona]",
    }
    base = layer_labels.get(layer, "[Memory]")
    return f"{base}[{memory_type}]"

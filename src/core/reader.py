from __future__ import annotations

from typing import Any

from src.core.interfaces import IBeliefStore, IReader


class Reader(IReader):

    def __init__(self, belief_store: IBeliefStore) -> None:
        self._belief_store = belief_store

    def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        beliefs = self._belief_store.get(conversation_id)
        messages: list[dict[str, Any]] = []
        current_tokens = 0

        for belief in reversed(beliefs):
            role = belief.source
            if role == "tool":
                role = "tool"
            content = belief.content
            estimated_tokens = max(1, len(content) // 4)

            if current_tokens + estimated_tokens > max_tokens:
                break

            messages.insert(0, {"role": role, "content": content})
            current_tokens += estimated_tokens

        return messages

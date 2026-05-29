from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import IBeliefStore, IReader

logger = logging.getLogger(__name__)


_ENCODING_CACHE: dict[str, Any] = {}


def _get_encoding(model: str = "gpt-4") -> Any:
    cached = _ENCODING_CACHE.get(model)
    if cached is not None:
        return cached
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model)
        _ENCODING_CACHE[model] = enc
        return enc
    except Exception:
        logger.warning("tiktoken unavailable, falling back to char/4 estimation")
        _ENCODING_CACHE[model] = None
        return None


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    if not text:
        return 1
    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


class Reader(IReader):
    def __init__(self, belief_store: IBeliefStore) -> None:
        self._belief_store = belief_store

    async def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        beliefs = await self._belief_store.get(conversation_id)
        messages: list[dict[str, Any]] = []
        current_tokens = 0

        for belief in reversed(beliefs):
            role = belief.source
            if role == "tool":
                role = "tool"
            content = belief.content
            estimated_tokens = estimate_tokens(content)

            if current_tokens + estimated_tokens > max_tokens:
                break

            messages.insert(0, {"role": role, "content": content})
            current_tokens += estimated_tokens

        return messages

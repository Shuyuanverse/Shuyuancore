"""基于 BeliefStore 的对话读取器 — 简单实现。

职责区分：
- Reader：从 IBeliefStore 获取 belief，按时间逆序组装为对话消息列表
- 与 src/memory/reader.py 的 BeliefReader 不同，这里仅做简单的时间排序组装
- BeliefReader 支持分层优先级检索和查询相关性排序
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import IBeliefStore, IReader

logger = logging.getLogger(__name__)


_ENCODING_CACHE: dict[str, Any] = {}


def get_real_callable_attr(obj: object, name: str) -> Any | None:
    """Return an actual callable attribute without accepting loose mock children."""
    class_attr = getattr(type(obj), name, None)
    if class_attr is not None:
        bound = getattr(obj, name, None)
        return bound if callable(bound) else None

    instance_attrs = getattr(obj, "__dict__", {})
    instance_attr = instance_attrs.get(name) if isinstance(instance_attrs, dict) else None
    return instance_attr if callable(instance_attr) else None


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
        if user_query:
            ebl_messages = await self._read_evidence_belief_context(
                conversation_id=conversation_id,
                user_query=user_query,
                max_tokens=max_tokens,
            )
            if ebl_messages:
                return ebl_messages

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

    async def read_rescue(
        self,
        conversation_id: str,
        user_query: str,
        max_tokens: int = 6000,
    ) -> list[dict[str, Any]]:
        ebl_messages = await self._read_evidence_belief_context(
            conversation_id=conversation_id,
            user_query=user_query,
            max_tokens=max_tokens,
            rescue=True,
        )
        if ebl_messages:
            return ebl_messages
        return await self.read(conversation_id, user_query=user_query, max_tokens=max_tokens)

    async def _read_evidence_belief_context(
        self,
        conversation_id: str,
        user_query: str,
        max_tokens: int,
        rescue: bool = False,
    ) -> list[dict[str, Any]]:
        ebl_reader = get_real_callable_attr(
            self._belief_store,
            "retrieve_evidence_belief_context",
        )
        if ebl_reader is None:
            return []

        try:
            bundle = await ebl_reader(
                conversation_id=conversation_id,
                query=user_query,
                max_tokens=max_tokens,
                rescue=rescue,
            )
            context = str(bundle.get("context") or "")
            if not context:
                return []
            diagnostics = bundle.get("diagnostics") or {}
            return [
                {
                    "role": "system",
                    "content": (
                        f"{context}\n\n"
                        f"Retrieval diagnostics: {diagnostics}"
                    ),
                }
            ]
        except Exception:
            logger.warning("evidence_belief_reader_failed", exc_info=True)
            return []

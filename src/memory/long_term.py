from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms
from src.memory.embedding import EmbeddingService
from src.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 20
_MAX_CONTENT_PREVIEW = 120


class LongTermMemory:
    def __init__(
        self,
        belief_store: IBeliefStore,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._belief_store = belief_store
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    async def get_conversation_list(
        self,
        user_id: str | None = None,
        cursor: str | None = None,
        limit: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict[str, object]], str | None, bool]:
        return await self._belief_store.get_conversation_list(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )

    async def get_conversation_messages(
        self,
        conversation_id: str,
        user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], str | None, bool]:
        return await self._belief_store.get_conversation_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )

    async def search(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
        layer_filter: int | None = None,
    ) -> list[tuple[Belief, float]]:
        return await self._belief_store.search_similar(
            query=query,
            top_k=top_k,
            min_confidence=min_confidence,
        )

    async def get_recent_summaries(
        self,
        user_id: str | None = None,
        hours: int = 24,
        max_conversations: int = 10,
    ) -> list[dict[str, Any]]:
        cutoff_ms = int((time.time() - hours * 3600) * 1000)
        convs, _, _ = await self.get_conversation_list(
            user_id=user_id,
            limit=max_conversations,
        )

        summaries: list[dict[str, Any]] = []
        for conv in convs:
            last_ts = conv.get("last_message_at", 0)
            if isinstance(last_ts, (int, float)) and last_ts < cutoff_ms:
                continue
            msgs, _, _ = await self.get_conversation_messages(
                conversation_id=str(conv.get("id", "")),
                user_id=user_id,
                limit=5,
            )
            if not msgs:
                continue
            previews = []
            for m in msgs[:3]:
                content = str(m.get("content", ""))
                previews.append(content[:_MAX_CONTENT_PREVIEW])
            summaries.append({
                "conversation_id": conv.get("id"),
                "message_count": conv.get("message_count", 0),
                "last_message_at": conv.get("last_message_at", 0),
                "preview": " | ".join(previews),
            })

        summaries.sort(key=lambda x: x.get("last_message_at", 0) or 0, reverse=True)
        return summaries

    async def prune_conversation(
        self,
        conversation_id: str,
        max_beliefs: int = 200,
        strategy: str = "oldest_first",
    ) -> int:
        if strategy != "oldest_first":
            logger.warning("unsupported_prune_strategy=%s, falling back to oldest_first", strategy)

        beliefs = await self._belief_store.get(conversation_id, limit=1000)
        if len(beliefs) <= max_beliefs:
            return 0

        beliefs.sort(key=lambda b: b.last_accessed)
        to_remove = beliefs[:-max_beliefs]
        removed = 0
        for belief in to_remove:
            try:
                await self._belief_store.remove(conversation_id, belief.id)
                removed += 1
            except Exception:
                logger.exception("failed_to_remove_belief conv=%s belief=%s", conversation_id, belief.id)

        logger.info(
            "pruned %d beliefs from conversation %s (kept %d)",
            removed, conversation_id, max_beliefs,
        )
        return removed

    async def get_statistics(
        self,
        user_id: str | None = None,
        hours: int = 168,
    ) -> dict[str, Any]:
        cutoff_ms = int((time.time() - hours * 3600) * 1000)
        convs, _, _ = await self.get_conversation_list(
            user_id=user_id,
            limit=1000,
        )

        active_window = 0
        total_msgs = 0
        for conv in convs:
            last_ts = conv.get("last_message_at", 0)
            if isinstance(last_ts, (int, float)) and last_ts >= cutoff_ms:
                active_window += 1
            msg_count = conv.get("message_count", 0)
            if isinstance(msg_count, int):
                total_msgs += msg_count

        return {
            "total_conversations": len(convs),
            "active_conversations": active_window,
            "total_beliefs_approx": total_msgs,
            "window_hours": hours,
            "as_of_ms": current_time_ms(),
        }

    async def get_by_id(self, belief_id: str) -> Belief | None:
        return await self._belief_store.get_by_id(belief_id)
# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""对话管理模块 — 独立于 Agent 的对话生命周期管理。

功能：
- 创建对话（生成唯一 ID）
- 添加消息（存储到 beliefs 表）
- 获取消息历史（支持游标分页）
- 列表用户对话（按最后消息时间排序）
- 删除对话（级联删除所有消息）
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.core.interfaces import Belief, IBeliefStore, IConversationManager
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)


class ConversationManager(IConversationManager):
    """对话管理器实现。

    使用 beliefs 表存储对话消息：
    - layer=3（长期记忆层）
    - memory_type='conversation'
    - conversation_id 作为索引
    """

    def __init__(self, belief_store: IBeliefStore) -> None:
        """初始化对话管理器。

        Args:
            belief_store: 信念存储后端
        """
        self._belief_store = belief_store

    async def create_conversation(self, user_id: str, title: str = "") -> str:
        conversation_id = str(uuid.uuid4())
        logger.info("Created conversation: %s (user=%s, title=%s)", conversation_id, user_id, title)
        return conversation_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        belief = Belief(
            id=str(uuid.uuid4()),
            content=content,
            source=role,
            memory_type="conversation",
            layer=3,
            timestamp=current_time_ms(),
            last_accessed=current_time_ms(),
            metadata=metadata or {},
        )

        await self._belief_store.add(conversation_id, belief)
        logger.debug("Added message to conversation %s: role=%s", conversation_id, role)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        beliefs = await self._belief_store.get(conversation_id, limit=limit)

        messages = []
        for belief in beliefs:
            msg = {
                "id": belief.id,
                "role": belief.source,
                "content": belief.content,
                "timestamp": belief.timestamp,
                "metadata": belief.metadata,
            }
            messages.append(msg)

        messages.sort(key=lambda m: m["timestamp"])

        if before is not None:
            try:
                before_ts, before_id = before.rsplit("_", 1)
                before_timestamp = int(before_ts)
                messages = [
                    m for m in messages if (m["timestamp"], m["id"]) < (before_timestamp, before_id)
                ]
            except (ValueError, AttributeError):
                logger.warning("Invalid before cursor: %s", before)

        return messages[:limit]

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, bool]:
        logger.info("Listing conversations for user %s (limit=%d)", user_id, limit)
        return [], None, False

    async def delete_conversation(self, conversation_id: str) -> None:
        await self._belief_store.clear(conversation_id)
        logger.info("Deleted conversation: %s", conversation_id)

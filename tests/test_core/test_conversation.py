# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""对话管理器单元测试。"""

import pytest
import pytest_asyncio

from src.core.conversation import ConversationManager
from src.core.interfaces import Belief, IBeliefStore


class MockBeliefStore(IBeliefStore):
    """模拟信念存储用于测试。"""

    def __init__(self) -> None:
        self._beliefs: dict[str, list[Belief]] = {}

    async def add(self, conversation_id: str, belief: Belief) -> str:
        if conversation_id not in self._beliefs:
            self._beliefs[conversation_id] = []
        self._beliefs[conversation_id].append(belief)
        return belief.id

    async def get(self, conversation_id: str, limit: int = 50) -> list[Belief]:
        beliefs = self._beliefs.get(conversation_id, [])
        return beliefs[:limit]

    async def get_by_id(self, belief_id: str) -> Belief | None:
        for beliefs in self._beliefs.values():
            for belief in beliefs:
                if belief.id == belief_id:
                    return belief
        return None

    async def update(self, belief: Belief) -> None:
        pass

    async def clear(self, conversation_id: str) -> None:
        if conversation_id in self._beliefs:
            del self._beliefs[conversation_id]

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        if conversation_id in self._beliefs:
            self._beliefs[conversation_id] = [
                b for b in self._beliefs[conversation_id] if b.id != belief_id
            ]

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


@pytest_asyncio.fixture
async def conv_mgr():
    """创建对话管理器测试夹具。"""
    store = MockBeliefStore()
    return ConversationManager(store)


@pytest.mark.asyncio
async def test_create_conversation(conv_mgr: ConversationManager) -> None:
    """测试创建对话。"""
    user_id = "test_user"
    title = "Test Conversation"

    conversation_id = await conv_mgr.create_conversation(user_id, title)

    assert conversation_id is not None
    assert len(conversation_id) == 36


@pytest.mark.asyncio
async def test_add_message(conv_mgr: ConversationManager) -> None:
    """测试添加消息。"""
    conversation_id = await conv_mgr.create_conversation("user1")

    await conv_mgr.add_message(
        conversation_id=conversation_id,
        role="user",
        content="Hello",
    )

    messages = await conv_mgr.get_messages(conversation_id)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_get_messages_pagination(conv_mgr: ConversationManager) -> None:
    """测试获取消息分页。"""
    conversation_id = await conv_mgr.create_conversation("user1")

    for i in range(10):
        await conv_mgr.add_message(
            conversation_id=conversation_id,
            role="user",
            content=f"Message {i}",
        )

    messages = await conv_mgr.get_messages(conversation_id, limit=5)
    assert len(messages) == 5

    before_cursor = f"{messages[-1]['timestamp']}_{messages[-1]['id']}"
    next_page = await conv_mgr.get_messages(conversation_id, limit=5, before=before_cursor)
    assert len(next_page) < 5


@pytest.mark.asyncio
async def test_list_conversations(conv_mgr: ConversationManager) -> None:
    """测试列表对话。"""
    user_id = "test_user"

    for i in range(5):
        await conv_mgr.create_conversation(user_id, f"Conversation {i}")

    conversations, next_cursor, has_more = await conv_mgr.list_conversations(user_id, limit=20)

    assert isinstance(conversations, list)
    assert next_cursor is None
    assert has_more is False


@pytest.mark.asyncio
async def test_delete_conversation(conv_mgr: ConversationManager) -> None:
    """测试删除对话。"""
    conversation_id = await conv_mgr.create_conversation("user1")

    await conv_mgr.add_message(
        conversation_id=conversation_id,
        role="user",
        content="Test message",
    )

    await conv_mgr.delete_conversation(conversation_id)

    messages = await conv_mgr.get_messages(conversation_id)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_add_message_with_metadata(conv_mgr: ConversationManager) -> None:
    """测试添加带元数据的消息。"""
    conversation_id = await conv_mgr.create_conversation("user1")

    metadata = {"tool_call": {"name": "search", "args": {"query": "test"}}}

    await conv_mgr.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content="Searching...",
        metadata=metadata,
    )

    messages = await conv_mgr.get_messages(conversation_id)
    assert len(messages) == 1
    assert messages[0]["metadata"] == metadata

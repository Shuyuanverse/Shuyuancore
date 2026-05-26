from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.interfaces import Belief
from src.memory.reader import BeliefReader


@pytest.fixture
def empty_store() -> AsyncMock:
    store = AsyncMock()
    store.get = AsyncMock(return_value=[])
    store.search_similar = AsyncMock(return_value=[])
    return store


@pytest.fixture
def populated_store() -> AsyncMock:
    store = AsyncMock()

    l1_beliefs = [
        Belief(
            id="l1_1", content="[identity] 我叫小明",
            source="user", confidence=0.95, base_confidence=0.95,
            layer=1, memory_type="identity",
            timestamp=1000, last_accessed=1000,
        ),
        Belief(
            id="l1_2", content="[preference] 我喜欢编程",
            source="user", confidence=0.85, base_confidence=0.85,
            layer=1, memory_type="preference",
            timestamp=1000, last_accessed=1000,
        ),
    ]
    l2_beliefs = [
        Belief(
            id="l2_1", content="[task] 正在开发AI项目",
            source="user", confidence=0.8, base_confidence=0.8,
            layer=2, memory_type="task",
            timestamp=1000, last_accessed=1000,
        ),
    ]
    l3_relevant = Belief(
        id="l3_1", content="[fact] Python是主要编程语言",
        source="user", confidence=0.7, base_confidence=0.7,
        layer=3, memory_type="fact",
        timestamp=1000, last_accessed=1000,
    )
    l3_beliefs = [
        l3_relevant,
        Belief(
            id="l3_2", content="[chat] 今天讨论了数据库设计",
            source="assistant", confidence=0.6, base_confidence=0.6,
            layer=3, memory_type="chat",
            timestamp=1000, last_accessed=1000,
        ),
    ]

    store.get = AsyncMock(return_value=l1_beliefs + l2_beliefs + l3_beliefs)
    store.search_similar = AsyncMock(return_value=[(l3_relevant, 0.85)])
    return store


class TestBeliefReader:

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_list(self, empty_store: AsyncMock) -> None:
        reader = BeliefReader(empty_store)
        result = await reader.read("conv_empty")
        assert result == []

    @pytest.mark.asyncio
    async def test_l1_beliefs_included_in_system_prompt_section(
        self, populated_store: AsyncMock,
    ) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated")
        system_messages = [m for m in result if m["role"] == "system"]
        assert any("[Core Memory]" in m["content"] for m in system_messages)

    @pytest.mark.asyncio
    async def test_l2_beliefs_included_in_working_memory_section(
        self, populated_store: AsyncMock,
    ) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated")
        contents = " ".join(m["content"] for m in result)
        assert "[Working Memory]" in contents

    @pytest.mark.asyncio
    async def test_sort_by_confidence_relevance(
        self, populated_store: AsyncMock,
    ) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated", user_query="Python")
        scores = []
        for msg in result:
            if "[Core Memory]" in msg["content"]:
                scores.append(0.95 * 1.0)
            elif "[Working Memory]" in msg["content"]:
                scores.append(0.8 * 0.9)
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_max_tokens_truncation(self, populated_store: AsyncMock) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated", max_tokens=1)
        assert len(result) <= 1

    @pytest.mark.asyncio
    async def test_returns_dict_format_compatible_with_llm(
        self, populated_store: AsyncMock,
    ) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated")
        for entry in result:
            assert isinstance(entry, dict)
            assert "role" in entry
            assert "content" in entry
            assert entry["role"] in ("system", "assistant")

    @pytest.mark.asyncio
    async def test_relevant_beliefs_included_via_search(
        self, populated_store: AsyncMock,
    ) -> None:
        reader = BeliefReader(populated_store)
        result = await reader.read("conv_populated", user_query="Python编程")
        contents = " ".join(m["content"] for m in result)
        assert "Python" in contents
        populated_store.search_similar.assert_awaited_once_with(
            "Python编程", top_k=5, min_confidence=0.1
        )

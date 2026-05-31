from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.interfaces import Belief
from src.tools.builtin.memory import MemoryTool


class TestMemoryTool:

    def test_memory_get_spec(self) -> None:
        tool = MemoryTool()
        spec = tool.get_spec()
        assert spec.name == "memory"
        assert spec.category == "memory"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_memory_validate_invalid_op(self) -> None:
        tool = MemoryTool()
        errors = await tool.validate({"operation": "invalid_op"})
        assert any("operation 必须是" in e for e in errors)

    @pytest.mark.asyncio
    async def test_memory_validate_missing_query(self) -> None:
        tool = MemoryTool()
        errors = await tool.validate({"operation": "search"})
        assert any("query" in e for e in errors)

    @pytest.mark.asyncio
    async def test_memory_execute_search(self) -> None:
        mock_store = MagicMock()
        mock_belief = Belief(
            id="belief-1",
            content="test content",
            source="user",
            layer=3,
            confidence=0.9,
            memory_type="chat",
            timestamp=1000000,
            status="active",
        )
        mock_store.search_similar = AsyncMock(
            return_value=[(mock_belief, 0.95)],
        )
        tool = MemoryTool(store=mock_store)
        result = await tool.execute(
            {"operation": "search", "query": "test", "limit": 5},
        )

        assert result.success is True
        assert result.data is not None
        assert len(result.data["results"]) == 1
        assert result.data["results"][0]["id"] == "belief-1"
        assert result.data["results"][0]["content"] == "test content"
        mock_store.search_similar.assert_awaited_once_with("test", top_k=5)

    @pytest.mark.asyncio
    async def test_memory_execute_write(self) -> None:
        mock_store = MagicMock()
        mock_store.add = AsyncMock(return_value="new-belief-id")
        tool = MemoryTool(store=mock_store)
        result = await tool.execute(
            {"operation": "write", "content": "new memory content", "layer": 3},
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["belief_id"] == "new-belief-id"
        assert result.data["layer"] == 3
        mock_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_memory_execute_delete(self) -> None:
        mock_store = MagicMock()
        mock_store.remove = AsyncMock()
        tool = MemoryTool(store=mock_store)
        result = await tool.execute(
            {"operation": "delete", "belief_id": "belief-to-delete"},
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["deleted"] == "belief-to-delete"
        mock_store.remove.assert_awaited_once_with(
            "default", "belief-to-delete",
        )
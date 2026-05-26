from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.interfaces import UpdateContext, UpdaterResult
from src.agents.sub_agent import SubAgent
from src.core.interfaces import Belief, IBeliefStore


class TestSubAgent:

    def _make_store(self) -> IBeliefStore:
        store = MagicMock(spec=IBeliefStore)
        store.get = AsyncMock(return_value=[])
        store.add = AsyncMock(return_value="belief-id")
        return store

    @pytest.mark.asyncio
    async def test_basic_run(self) -> None:
        store = self._make_store()
        sub = SubAgent(belief_store=store, scope="test_scope")
        result = await sub.run("task", "test_scope", {"conversation_id": "c1"})
        assert "子代理" in result
        assert "task" in result
        store.add.assert_called()

    @pytest.mark.asyncio
    async def test_writes_belief_with_scope_prefix(self) -> None:
        store = self._make_store()
        sub = SubAgent(belief_store=store, scope="research")
        await sub.run("research topic", "research", {"conversation_id": "c1"})
        store.add.assert_called()
        belief = store.add.call_args[0][1]
        assert belief.source == "sub_agent:research"

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self) -> None:
        import asyncio
        from unittest.mock import patch

        store = self._make_store()
        sub = SubAgent(belief_store=store, scope="slow", timeout=5)

        async def fake_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        with patch("src.agents.sub_agent.asyncio.wait_for", side_effect=fake_wait_for):
            result = await sub.run("task", "slow", {"conversation_id": "c1"})
        assert result == ""

    @pytest.mark.asyncio
    async def test_belief_write_failure_handled(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.get = AsyncMock(return_value=[])
        store.add = AsyncMock(side_effect=RuntimeError("db down"))
        sub = SubAgent(belief_store=store, scope="test")
        result = await sub.run("task", "test", {"conversation_id": "c1"})
        assert "子代理" in result

    @pytest.mark.asyncio
    async def test_scope_fallback(self) -> None:
        store = self._make_store()
        sub = SubAgent(belief_store=store, scope="default")
        await sub.run("task", "override", {"conversation_id": "c1"})
        store.add.assert_called()
        belief = store.add.call_args[0][1]
        assert belief.source == "sub_agent:override"
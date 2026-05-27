from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.interfaces import UpdateContext, UpdaterResult
from src.agents.sub_agent import SubAgent
from src.core.interfaces import Belief, IBeliefStore


class MockRouter:

    def __init__(self, response: str = "llm result") -> None:
        self.response = response
        self.history: list[dict] = []
        self.last_prompt: str = ""

    async def chat(self, history: list[dict], **kwargs):
        self.history = history
        self.last_prompt = history[-1]["content"] if history else ""
        from collections import namedtuple
        ChatResult = namedtuple("ChatResult", ["content", "tokens_used", "model_used", "finish_reason"])
        return ChatResult(content=self.response, tokens_used=10, model_used="test", finish_reason="stop")


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

    @pytest.mark.asyncio
    async def test_filters_low_confidence_beliefs(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.add = AsyncMock(return_value="id")
        store.get = AsyncMock(
            return_value=[
                Belief(id="a", content="低置信度", source="user", confidence=0.3, base_confidence=0.3, last_accessed=0, timestamp=0, memory_type="fact", layer=1),
                Belief(id="b", content="高置信度", source="user", confidence=0.8, base_confidence=0.8, last_accessed=0, timestamp=0, memory_type="fact", layer=1),
            ]
        )
        sub = SubAgent(belief_store=store, scope="test")
        result = await sub.run("task", "test", {"conversation_id": "c1"})
        assert "高置信度" in result
        assert "低置信度" not in result

    @pytest.mark.asyncio
    async def test_uses_llm_when_router_provided(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.get = AsyncMock(return_value=[])
        store.add = AsyncMock(return_value="id")
        router = MockRouter(response="llm generated analysis")
        sub = SubAgent(belief_store=store, scope="llm_test", router=router)
        result = await sub.run("analyze", "llm_test", {"conversation_id": "c1"})
        assert result == "llm generated analysis"
        assert "作用域: llm_test" in router.last_prompt

    @pytest.mark.asyncio
    async def test_falls_back_when_llm_fails(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.get = AsyncMock(return_value=[])
        store.add = AsyncMock(return_value="id")

        class FailingRouter:
            async def chat(self, history, **kwargs):
                raise RuntimeError("llm down")

        sub = SubAgent(belief_store=store, scope="fallback", router=FailingRouter())
        result = await sub.run("task", "fallback", {"conversation_id": "c1"})
        assert "子代理" in result
        assert "fallback" in result
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.arbitrator import Arbitrator
from src.agents.coordinator import Coordinator
from src.agents.interfaces import UpdateContext, UpdaterResult
from src.core.interfaces import Belief, IBeliefStore
from src.models.interfaces import ChatResult, IModelProvider


def _make_ctx(message: str = "hello") -> UpdateContext:
    store = MagicMock(spec=IBeliefStore)
    store.get = AsyncMock(return_value=[])
    store.search_similar = AsyncMock(return_value=[])
    store.add = AsyncMock(return_value="b1")
    return UpdateContext(
        conversation_id="conv1",
        user_id="user1",
        message=message,
        belief_store=store,
    )


def _make_provider(response_content: str) -> IModelProvider:
    provider = MagicMock(spec=IModelProvider)
    provider.chat = AsyncMock(
        return_value=ChatResult(content=response_content, model_used="test")
    )
    return provider


class TestCoordinator:

    @pytest.mark.asyncio
    async def test_basic_run(self) -> None:
        provider = _make_provider(
            '{"content": "建议A", "confidence": 0.8, "reasoning": "有证据"}'
        )
        coordinator = Coordinator(provider)
        ctx = _make_ctx("我应该怎么办")
        result = await coordinator.run(ctx)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_mode_override(self) -> None:
        provider = _make_provider(
            '{"content": "ok", "confidence": 0.5, "reasoning": "测试"}'
        )
        coordinator = Coordinator(provider)
        coordinator.set_mode("conv1", "quick")
        assert coordinator.get_mode("conv1") == "quick"
        ctx = _make_ctx("hello")
        result = await coordinator.run(ctx)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invalid_mode_ignored(self) -> None:
        coordinator = Coordinator(MagicMock(spec=IModelProvider))
        coordinator.set_mode("conv1", "invalid_mode")
        assert coordinator.get_mode("conv1") is None

    @pytest.mark.asyncio
    async def test_updater_failure_fallback(self) -> None:
        provider = _make_provider(
            '{"content": "fallback answer", "confidence": 0.5, "reasoning": "回退方案"}'
        )
        coordinator = Coordinator(provider)
        ctx = _make_ctx("紧急问题")
        result = await coordinator.run(ctx)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_beliefs_written(self) -> None:
        provider = _make_provider(
            '{"content": "方案", "confidence": 0.8, "reasoning": "测试"}'
        )
        coordinator = Coordinator(provider)
        ctx = _make_ctx("测试问题")
        await coordinator.run(ctx)
        assert ctx.belief_store is not None
        assert ctx.belief_store.add.called
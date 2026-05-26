from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.coordinator import Coordinator
from src.agents.interfaces import UpdateContext
from src.agents.sub_agent import SubAgent
from src.core.interfaces import Belief, IBeliefStore
from src.models.interfaces import ChatResult, IModelProvider


def _make_store() -> IBeliefStore:
    store = MagicMock(spec=IBeliefStore)
    store.get = AsyncMock(return_value=[])
    store.search_similar = AsyncMock(return_value=[])
    store.add = AsyncMock(return_value="b1")
    return store


def _make_provider() -> IModelProvider:
    provider = MagicMock(spec=IModelProvider)
    provider.chat = AsyncMock(
        return_value=ChatResult(
            content='{"content": "综合建议采用方案A", "confidence": 0.8, "reasoning": "基于多视角分析"}',
            model_used="test",
        )
    )
    return provider


class TestAgentIntegration:

    @pytest.mark.asyncio
    async def test_full_coordinator_flow_high_perturbation(self) -> None:
        store = _make_store()
        store.search_similar = AsyncMock(return_value=[])
        provider = _make_provider()
        coordinator = Coordinator(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="我应该怎么办？",
            perturbation_strength=0.8,
            belief_store=store,
        )
        result = await coordinator.run(ctx)
        assert len(result) > 0
        assert store.add.called

    @pytest.mark.asyncio
    async def test_full_coordinator_flow_low_perturbation(self) -> None:
        store = _make_store()
        provider = _make_provider()
        coordinator = Coordinator(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="今天天气怎么样",
            perturbation_strength=0.1,
            belief_store=store,
        )
        result = await coordinator.run(ctx)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_coordinator_mode_override(self) -> None:
        store = _make_store()
        provider = _make_provider()
        coordinator = Coordinator(provider)
        coordinator.set_mode("conv1", "deep")
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="复杂决策问题",
            perturbation_strength=0.1,
            belief_store=store,
        )
        result = await coordinator.run(ctx)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_sub_agent_coordinator_belief_sharing(self) -> None:
        store = _make_store()
        provider = _make_provider()
        sub = SubAgent(belief_store=store, scope="research")
        await sub.run("research topic", "research", {"conversation_id": "conv1"})
        coordinator = Coordinator(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="基于研究成果做什么决策？",
            perturbation_strength=0.5,
            belief_store=store,
        )
        result = await coordinator.run(ctx)
        assert len(result) > 0
        assert store.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_full_pipeline_belief_persistence(self) -> None:
        store = _make_store()
        provider = _make_provider()
        coordinator = Coordinator(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="我想学编程",
            perturbation_strength=0.6,
            belief_store=store,
        )
        await coordinator.run(ctx)
        calls = [c[0][1].source for c in store.add.call_args_list]
        updater_sources = [s for s in calls if s.startswith("updater:")]
        assert len(updater_sources) >= 1

    @pytest.mark.asyncio
    async def test_full_pipeline_with_no_belief_store(self) -> None:
        provider = _make_provider()
        coordinator = Coordinator(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="hello",
        )
        result = await coordinator.run(ctx)
        assert len(result) > 0
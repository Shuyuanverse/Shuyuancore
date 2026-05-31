from __future__ import annotations

import pytest

from src.core.belief_store import BeliefStore
from src.core.interfaces import Belief


class TestBeliefStore:

    @pytest.mark.asyncio
    async def test_add_and_get(self) -> None:
        store = BeliefStore()
        belief = Belief(
            id="b1", content="hello", source="user", timestamp=1000
        )
        await store.add("conv_1", belief)
        beliefs = await store.get("conv_1")
        assert len(beliefs) == 1
        assert beliefs[0].content == "hello"
        assert beliefs[0].source == "user"

    @pytest.mark.asyncio
    async def test_get_empty_conversation(self) -> None:
        store = BeliefStore()
        beliefs = await store.get("nonexistent")
        assert beliefs == []

    @pytest.mark.asyncio
    async def test_get_with_limit(self) -> None:
        store = BeliefStore()
        for i in range(10):
            await store.add(
                "conv_1",
                Belief(
                    id=f"b{i}",
                    content=f"msg {i}",
                    source="user",
                    timestamp=i,
                ),
            )
        beliefs = await store.get("conv_1", limit=3)
        assert len(beliefs) == 3
        assert beliefs[-1].content == "msg 9"

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        store = BeliefStore()
        await store.add(
            "conv_1",
            Belief(id="b1", content="hello", source="user", timestamp=1),
        )
        await store.clear("conv_1")
        assert await store.get("conv_1") == []

    @pytest.mark.asyncio
    async def test_clear_nonexistent(self) -> None:
        store = BeliefStore()
        await store.clear("nonexistent")

    @pytest.mark.asyncio
    async def test_remove(self) -> None:
        store = BeliefStore()
        await store.add(
            "conv_1",
            Belief(id="b1", content="one", source="user", timestamp=1),
        )
        await store.add(
            "conv_1",
            Belief(id="b2", content="two", source="user", timestamp=2),
        )
        await store.remove("conv_1", "b1")
        beliefs = await store.get("conv_1")
        assert len(beliefs) == 1
        assert beliefs[0].id == "b2"

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self) -> None:
        store = BeliefStore()
        await store.remove("conv_1", "b1")

    @pytest.mark.asyncio
    async def test_isolated_conversations(self) -> None:
        store = BeliefStore()
        await store.add(
            "conv_1",
            Belief(id="b1", content="hello", source="user", timestamp=1),
        )
        await store.add(
            "conv_2",
            Belief(id="b2", content="world", source="user", timestamp=1),
        )
        assert len(await store.get("conv_1")) == 1
        assert len(await store.get("conv_2")) == 1

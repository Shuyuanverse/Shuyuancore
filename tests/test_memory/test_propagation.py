from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.interfaces import Belief
from src.memory.propagation import overthrow, propagate_confidence


@pytest.fixture
def mock_store() -> AsyncMock:
    store = AsyncMock()
    store.get_by_id = AsyncMock()
    store.update = AsyncMock()
    return store


class TestPropagateConfidence:

    @pytest.mark.asyncio
    async def test_propagate_updates_confidence_only(self, mock_store: AsyncMock) -> None:
        belief = Belief(
            id="b1", content="test", source="user",
            confidence=0.7, base_confidence=0.7,
            layer=1,
        )
        mock_store.get_by_id.return_value = belief

        await propagate_confidence(mock_store, "b1", 0.1)

        assert belief.confidence == pytest.approx(0.8)
        assert belief.base_confidence == pytest.approx(0.7)
        mock_store.update.assert_awaited_once_with(belief)

    @pytest.mark.asyncio
    async def test_propagate_follows_depends_on_chain(self, mock_store: AsyncMock) -> None:
        parent = Belief(
            id="parent", content="parent", source="user",
            confidence=0.7, base_confidence=0.7,
            layer=1, depends_on=["child"],
        )
        child = Belief(
            id="child", content="child", source="user",
            confidence=0.5, base_confidence=0.5,
            layer=3,
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            mapping = {"parent": parent, "child": child}
            return mapping.get(belief_id)

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        await propagate_confidence(mock_store, "parent", 0.2)

        assert parent.confidence == pytest.approx(0.9)
        assert child.confidence == pytest.approx(0.5 + 0.2 * 0.3)

    @pytest.mark.asyncio
    async def test_propagate_follows_child_belief_ids(self, mock_store: AsyncMock) -> None:
        parent = Belief(
            id="parent", content="parent", source="user",
            confidence=0.6, base_confidence=0.6,
            layer=1, child_belief_ids=["child"],
        )
        child = Belief(
            id="child", content="child", source="user",
            confidence=0.4, base_confidence=0.4,
            layer=3,
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            mapping = {"parent": parent, "child": child}
            return mapping.get(belief_id)

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        await propagate_confidence(mock_store, "parent", 0.3)

        assert parent.confidence == pytest.approx(0.9)
        assert child.confidence == pytest.approx(0.4 + 0.3 * 0.2)

    @pytest.mark.asyncio
    async def test_propagate_clamps_to_zero_one_range(self, mock_store: AsyncMock) -> None:
        belief = Belief(
            id="b1", content="test", source="user",
            confidence=0.95, base_confidence=0.95,
            layer=1,
        )
        mock_store.get_by_id.return_value = belief

        await propagate_confidence(mock_store, "b1", 0.1)

        assert belief.confidence == 1.0
        assert belief.base_confidence == pytest.approx(0.95)


class TestOverthrow:

    @pytest.mark.asyncio
    async def test_overthrow_marks_old_as_superseded(self, mock_store: AsyncMock) -> None:
        old = Belief(
            id="old", content="old belief", source="user",
            confidence=0.8, base_confidence=0.8,
            layer=1,
        )
        new = Belief(
            id="new", content="new belief", source="user",
            confidence=0.9, base_confidence=0.9,
            layer=1,
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            mapping = {"old": old, "new": new}
            return mapping.get(belief_id)

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        await overthrow(mock_store, "old", "new", "better information")

        assert old.status == "superseded"
        assert old.superseded_by == "new"

    @pytest.mark.asyncio
    async def test_overthrow_links_new_to_old_depends_on(self, mock_store: AsyncMock) -> None:
        old = Belief(
            id="old", content="old belief", source="user",
            confidence=0.8, base_confidence=0.8,
            layer=1, depends_on=["dep1"],
        )
        new = Belief(
            id="new", content="new belief", source="user",
            confidence=0.9, base_confidence=0.9,
            layer=1, depends_on=[],
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            mapping = {"old": old, "new": new}
            return mapping.get(belief_id)

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        await overthrow(mock_store, "old", "new", "update")

        assert "dep1" in new.depends_on
        assert new.metadata.get("overthrow_reason") == "update"
        assert new.metadata.get("supersedes") == "old"

    @pytest.mark.asyncio
    async def test_overthrow_raises_on_missing_old(self, mock_store: AsyncMock) -> None:
        mock_store.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found for overthrow"):
            await overthrow(mock_store, "nonexistent", "new", "reason")

    @pytest.mark.asyncio
    async def test_overthrow_raises_on_missing_new(self, mock_store: AsyncMock) -> None:
        old = Belief(
            id="old", content="old", source="user",
            confidence=0.8, base_confidence=0.8,
            layer=1,
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            return old if belief_id == "old" else None

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        with pytest.raises(ValueError, match="not found for overthrow"):
            await overthrow(mock_store, "old", "missing_new", "reason")

    @pytest.mark.asyncio
    async def test_circular_dependency_protection(self, mock_store: AsyncMock) -> None:
        b1 = Belief(
            id="b1", content="b1", source="user",
            confidence=0.7, base_confidence=0.7,
            layer=1, depends_on=["b2"],
        )
        b2 = Belief(
            id="b2", content="b2", source="user",
            confidence=0.6, base_confidence=0.6,
            layer=1, depends_on=["b1"],
        )

        async def get_by_id_side_effect(belief_id: str) -> Belief | None:
            mapping = {"b1": b1, "b2": b2}
            return mapping.get(belief_id)

        mock_store.get_by_id.side_effect = get_by_id_side_effect

        await propagate_confidence(mock_store, "b1", 0.1)

        assert b1.confidence == pytest.approx(0.8)
        assert b2.confidence == pytest.approx(0.6 + 0.1 * 0.3)
        assert mock_store.update.await_count == 2, "Should only update b1 and b2 once each"

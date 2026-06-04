from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.interfaces import Belief
from src.memory.belief_store import PersistentBeliefStore


@pytest.fixture
async def store() -> PersistentBeliefStore:
    s = PersistentBeliefStore(db_path=":memory:")
    await s._get_conn()
    return s


@pytest.mark.usefixtures("store")
class TestPersistentBeliefStore:

    @pytest.mark.asyncio
    async def test_add_and_get(self, store: PersistentBeliefStore) -> None:
        belief = Belief(
            id="b1", content="hello", source="user",
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", belief)
        beliefs = await store.get("conv_1")
        assert len(beliefs) == 1
        assert beliefs[0].content == "hello"
        assert beliefs[0].source == "user"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_belief(self, store: PersistentBeliefStore) -> None:
        belief = Belief(
            id="b1", content="find me", source="user",
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", belief)
        result = await store.get_by_id("b1")
        assert result is not None
        assert result.content == "find me"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_missing(self, store: PersistentBeliefStore) -> None:
        result = await store.get_by_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_respects_limit(self, store: PersistentBeliefStore) -> None:
        for i in range(10):
            belief = Belief(
                id=f"b{i}", content=f"msg {i}", source="user",
                timestamp=i, last_accessed=i,
            )
            await store.add("conv_1", belief)

        beliefs = await store.get("conv_1", limit=3)
        assert len(beliefs) == 3

    @pytest.mark.asyncio
    async def test_update_modifies_fields(self, store: PersistentBeliefStore) -> None:
        belief = Belief(
            id="b1", content="original", source="user",
            confidence=0.5, base_confidence=0.5,
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", belief)

        belief.content = "updated"
        belief.confidence = 0.9
        await store.update(belief)

        result = await store.get_by_id("b1")
        assert result is not None
        assert result.content == "updated"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_remove_deletes_belief(self, store: PersistentBeliefStore) -> None:
        belief = Belief(
            id="b1", content="delete me", source="user",
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", belief)
        await store.remove("conv_1", "b1")

        result = await store.get_by_id("b1")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_similar_fallback_to_like(self, store: PersistentBeliefStore) -> None:
        belief = Belief(
            id="b1", content="Python programming is fun", source="user",
            confidence=0.9, base_confidence=0.9,
            timestamp=1000, last_accessed=1000,
            status="active",
        )
        await store.add("conv_1", belief)

        results = await store.search_similar("Python", top_k=5, min_confidence=0.1)
        assert len(results) >= 1
        assert results[0][0].id == "b1"

    @pytest.mark.asyncio
    async def test_search_similar_empty_query(self, store: PersistentBeliefStore) -> None:
        results = await store.search_similar("", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_raw_chat_belief_is_mirrored_to_evidence(
        self, store: PersistentBeliefStore,
    ) -> None:
        belief = Belief(
            id="raw1",
            content="Alice moved to Paris on 2024-05-01.",
            source="user",
            timestamp=1000,
            last_accessed=1000,
            conversation_date="2024-05-01",
        )

        await store.add("conv_ebl", belief, user_id="user-1")

        stored = await store.get_by_id("raw1")
        evidence = await store.get_evidence_by_id("E-raw1")
        assert stored is not None
        assert stored.metadata["evidence_id"] == "E-raw1"
        assert evidence is not None
        assert evidence["content"] == belief.content
        assert evidence["speaker"] == "user"
        assert evidence["conversation_date"] == "2024-05-01"

    @pytest.mark.asyncio
    async def test_structured_belief_infers_recent_evidence_ids(
        self, store: PersistentBeliefStore,
    ) -> None:
        raw = Belief(
            id="raw2",
            content="Mira said her preferred coding language is Rust.",
            source="user",
            timestamp=1000,
            last_accessed=1000,
        )
        structured = Belief(
            id="fact1",
            content="Mira prefers Rust for coding.",
            source="user",
            memory_type="preference",
            layer=1,
            timestamp=1100,
            last_accessed=1100,
        )

        await store.add("conv_ebl", raw)
        await store.add("conv_ebl", structured)

        saved = await store.get_by_id("fact1")
        assert saved is not None
        assert saved.metadata["evidence_ids"] == ["E-raw2"]

    @pytest.mark.asyncio
    async def test_evidence_belief_context_retrieves_raw_evidence(
        self, store: PersistentBeliefStore,
    ) -> None:
        belief = Belief(
            id="raw3",
            content="Mira adopted the codename Solstice on 2025-02-03.",
            source="user",
            timestamp=1000,
            last_accessed=1000,
            conversation_date="2025-02-03",
        )
        await store.add("conv_ebl", belief)

        bundle = await store.retrieve_evidence_belief_context(
            conversation_id="conv_ebl",
            query="What codename did Mira adopt on 2025-02-03?",
        )

        evidence_text = "\n".join(str(item["content"]) for item in bundle["evidence"])
        assert "Solstice" in evidence_text
        assert bundle["diagnostics"]["retrieved_evidence_count"] >= 1
        assert "Evidence Ledger" in bundle["context"]

    @pytest.mark.asyncio
    async def test_linked_belief_expands_to_evidence(
        self, store: PersistentBeliefStore,
    ) -> None:
        raw = Belief(
            id="raw4",
            content="The user prefers jasmine tea during long debugging sessions.",
            source="user",
            timestamp=1000,
            last_accessed=1000,
        )
        structured = Belief(
            id="pref1",
            content="The user has a jasmine tea preference.",
            source="user",
            memory_type="preference",
            layer=1,
            timestamp=1100,
            last_accessed=1100,
            metadata={"evidence_ids": ["E-raw4"]},
        )

        await store.add("conv_ebl", raw)
        await store.add("conv_ebl", structured)

        bundle = await store.retrieve_evidence_belief_context(
            conversation_id="conv_ebl",
            query="Which preference mentions jasmine tea?",
        )

        assert any(item["evidence_id"] == "E-raw4" for item in bundle["evidence"])
        assert bundle["diagnostics"]["linked_evidence_count"] >= 1

    @pytest.mark.asyncio
    async def test_temporal_neighbor_evidence_is_included(
        self, store: PersistentBeliefStore,
    ) -> None:
        await store.add("conv_ebl", Belief(
            id="raw5a",
            content="Before the appointment, Jordan booked a hotel near the embassy.",
            source="user",
            timestamp=1000,
            last_accessed=1000,
        ))
        await store.add("conv_ebl", Belief(
            id="raw5b",
            content="Jordan scheduled a visa office appointment for Monday.",
            source="user",
            timestamp=2000,
            last_accessed=2000,
        ))
        await store.add("conv_ebl", Belief(
            id="raw5c",
            content="After that, Jordan arranged a taxi for the interview day.",
            source="user",
            timestamp=3000,
            last_accessed=3000,
        ))

        bundle = await store.retrieve_evidence_belief_context(
            conversation_id="conv_ebl",
            query="What was Jordan's visa office appointment?",
        )

        evidence_ids = {item["evidence_id"] for item in bundle["evidence"]}
        assert "E-raw5b" in evidence_ids
        assert "E-raw5a" in evidence_ids or "E-raw5c" in evidence_ids

    @pytest.mark.asyncio
    async def test_propagate_confidence_calls_propagation(
        self, store: PersistentBeliefStore,
    ) -> None:
        belief = Belief(
            id="b1", content="test", source="user",
            confidence=0.7, base_confidence=0.7,
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", belief)

        with patch(
            "src.memory.belief_store.propagation_propagate",
            new_callable=AsyncMock,
        ) as mock_prop:
            await store.propagate_confidence("b1", 0.1)
            mock_prop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_overthrow_calls_propagation(
        self, store: PersistentBeliefStore,
    ) -> None:
        old = Belief(
            id="old", content="old", source="user",
            timestamp=1000, last_accessed=1000,
        )
        new = Belief(
            id="new", content="new", source="user",
            timestamp=1000, last_accessed=1000,
        )
        await store.add("conv_1", old)
        await store.add("conv_1", new)

        with patch(
            "src.memory.belief_store.propagation_overthrow",
            new_callable=AsyncMock,
        ) as mock_ovt:
            await store.overthrow("old", "new", "reason")
            mock_ovt.assert_awaited_once_with(store, "old", "new", "reason")

    @pytest.mark.asyncio
    async def test_close_clears_connection(self, store: PersistentBeliefStore) -> None:
        assert store._conn is not None
        await store.close()
        assert store._conn is None

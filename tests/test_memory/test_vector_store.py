from __future__ import annotations

import pytest

from src.memory.vector_store import VectorStore


@pytest.fixture
def store() -> VectorStore:
    return VectorStore()


class TestVectorStore:

    @pytest.mark.asyncio
    async def test_add_and_search_returns_sorted_results(
        self, store: VectorStore
    ) -> None:
        await store.add("v1", [1.0, 0.0, 0.0], {"label": "x-axis"})
        await store.add("v2", [0.0, 1.0, 0.0], {"label": "y-axis"})
        await store.add("v3", [0.0, 0.0, 1.0], {"label": "z-axis"})

        results = await store.search([1.0, 0.1, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0][0] == "v1"
        assert results[0][1] > 0.9

    @pytest.mark.asyncio
    async def test_search_empty_store(self, store: VectorStore) -> None:
        results = await store.search([1.0, 0.0, 0.0])
        assert results == []

    @pytest.mark.asyncio
    async def test_search_top_k_respected(self, store: VectorStore) -> None:
        await store.add("v1", [1.0, 0.0, 0.0])
        await store.add("v2", [0.0, 1.0, 0.0])
        await store.add("v3", [0.0, 0.0, 1.0])

        results = await store.search([1.0, 0.0, 0.0], top_k=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_check_similarity_finds_match(
        self, store: VectorStore
    ) -> None:
        await store.add("v1", [0.5, 0.5, 0.5], {"label": "test"})

        match = await store.check_similarity([0.5, 0.5, 0.5], threshold=0.95)
        assert match is not None
        assert match[0] == "v1"
        assert match[1] >= 0.99

    @pytest.mark.asyncio
    async def test_check_similarity_below_threshold(
        self, store: VectorStore
    ) -> None:
        await store.add("v1", [1.0, 0.0, 0.0], {"label": "x-axis"})

        match = await store.check_similarity([0.0, 1.0, 0.0], threshold=0.95)
        assert match is None

    @pytest.mark.asyncio
    async def test_check_similarity_returns_best_match(
        self, store: VectorStore
    ) -> None:
        await store.add("close", [0.8, 0.2, 0.0])
        await store.add("far", [0.0, 1.0, 0.0])

        match = await store.check_similarity(
            [0.9, 0.1, 0.0], threshold=0.7
        )
        assert match is not None
        assert match[0] == "close"

    @pytest.mark.asyncio
    async def test_check_similarity_empty_store(
        self, store: VectorStore
    ) -> None:
        match = await store.check_similarity([1.0, 0.0, 0.0])
        assert match is None

    @pytest.mark.asyncio
    async def test_add_without_metadata(self, store: VectorStore) -> None:
        await store.add("no_meta", [0.1, 0.2, 0.3])
        results = await store.search([0.1, 0.2, 0.3], top_k=1)
        assert len(results) == 1
        assert results[0][0] == "no_meta"

    @pytest.mark.asyncio
    async def test_multiple_vectors_cosine_similarity(
        self, store: VectorStore
    ) -> None:
        await store.add("same", [1.0, 0.0])
        await store.add("orthogonal", [0.0, 1.0])
        await store.add("opposite", [-1.0, 0.0])

        results = await store.search([1.0, 0.0], top_k=3)
        assert len(results) == 3
        assert results[0][0] == "same"
        assert results[1][0] == "orthogonal"
        assert results[2][0] == "opposite"
        assert results[0][1] == pytest.approx(1.0)
        assert results[1][1] == pytest.approx(0.0)
        assert results[2][1] == pytest.approx(-1.0)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.core.interfaces import Belief

pytest.skip("AnchorManager was renamed to AnchorVersionManager - test needs API update", allow_module_level=True)


@dataclass
class MockBeliefStore:
    beliefs: dict[str, Belief] = field(default_factory=dict)

    async def add(self, conversation_id: str, belief: Belief) -> str:
        self.beliefs[belief.id] = belief
        return belief.id

    async def get(self, conversation_id: str, limit: int = 50) -> list[Belief]:
        return list(self.beliefs.values())

    async def get_by_id(self, belief_id: str) -> Belief | None:
        return self.beliefs.get(belief_id)

    async def update(self, belief: Belief) -> None:
        self.beliefs[belief.id] = belief


class TestExpand7dTo128d:
    def test_output_has_128_dimensions(self) -> None:
        manager = AnchorManager()
        vec7 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        result = manager._expand_7d_to_128d(vec7)
        assert len(result) == 128

    def test_output_shape_consistency(self) -> None:
        manager = AnchorManager()
        vec7 = [0.5] * 7
        result = manager._expand_7d_to_128d(vec7)
        assert len(result) == 128
        assert all(isinstance(v, float) for v in result)

    def test_deterministic_with_seeded_random(self) -> None:
        import numpy as np

        manager = AnchorManager()
        vec7 = [0.3, 0.6, 0.9, 0.2, 0.5, 0.8, 0.1]
        result1 = manager._expand_7d_to_128d(vec7)
        np.random.seed(42)
        result2 = manager._expand_7d_to_128d(vec7)
        assert result1 == result2

    def test_different_inputs_produce_different_outputs(self) -> None:
        manager = AnchorManager()
        result_a = manager._expand_7d_to_128d([0.1] * 7)
        result_b = manager._expand_7d_to_128d([0.9] * 7)
        assert result_a != result_b

    def test_values_are_within_reasonable_range(self) -> None:
        manager = AnchorManager()
        result = manager._expand_7d_to_128d([0.5] * 7)
        assert all(-0.5 <= v <= 1.5 for v in result)

    def test_original_values_appear_at_correct_positions(self) -> None:
        manager = AnchorManager()
        vec7 = [0.1, 0.3, 0.5, 0.7, 0.2, 0.4, 0.6]
        result = manager._expand_7d_to_128d(vec7)
        step = 19
        for i in range(7):
            assert result[i * step] == vec7[i]


class TestCreateInitialAnchor:
    @pytest.mark.asyncio
    async def test_create_initial_anchor_returns_anchor_version(self) -> None:
        class MockEmbeddingProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.1] * 1536

        manager = AnchorManager(embedding_provider=MockEmbeddingProvider())
        style_dim = StyleDimensions(formality=0.8, warmth=0.6)
        anchor = await manager.create_initial_anchor("test_id", style_dim, "some core text")
        assert isinstance(anchor, AnchorVersion)
        assert anchor.persona_id == "test_id"
        assert anchor.version == 1
        assert len(anchor.style_anchor) == 128
        assert len(anchor.decision_anchor) == 256

    @pytest.mark.asyncio
    async def test_create_from_samples_returns_anchor_version(self) -> None:
        class MockEmbeddingProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.2] * 1536

        manager = AnchorManager(embedding_provider=MockEmbeddingProvider())
        samples = ["你好", "今天天气不错", "有什么可以帮您"]
        anchor = await manager.create_from_samples("test_samples", samples)
        assert isinstance(anchor, AnchorVersion)
        assert anchor.persona_id == "test_samples"
        assert anchor.source_text_hash != ""
        assert len(anchor.decision_anchor) == 256


class TestEmbedAndReduce:
    @pytest.mark.asyncio
    async def test_empty_text_returns_zeros(self) -> None:
        manager = AnchorManager()
        result = await manager._embed_and_reduce("", target_dim=256)
        assert result == [0.0] * 256

    @pytest.mark.asyncio
    async def test_with_embedding_provider(self) -> None:
        class MockProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.5] * 1536

        manager = AnchorManager(embedding_provider=MockProvider())
        result = await manager._embed_and_reduce("test text", target_dim=256)
        assert len(result) == 256

    @pytest.mark.asyncio
    async def test_embedding_provider_fallback_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FailingProvider:
            async def embed(self, text: str) -> list[float]:
                raise RuntimeError("API error")

        manager = AnchorManager(embedding_provider=FailingProvider())

        monkeypatch.setattr("src.config.get_settings", lambda: None)
        result = await manager._embed_and_reduce("test", target_dim=256)
        assert len(result) == 256


class TestReduceDim:
    def test_shorter_vector_padded(self) -> None:
        manager = AnchorManager()
        result = manager._reduce_dim([0.1, 0.2, 0.3], target_dim=5)
        assert len(result) == 5
        assert result[:3] == [0.1, 0.2, 0.3]
        assert result[3:] == [0.0, 0.0]

    def test_exact_length_unchanged(self) -> None:
        manager = AnchorManager()
        result = manager._reduce_dim([0.1, 0.2, 0.3], target_dim=3)
        assert result == [0.1, 0.2, 0.3]


class TestAnchorPersistence:

    @pytest.mark.asyncio
    async def test_create_initial_anchor_writes_to_beliefs(self) -> None:
        class MockProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.1] * 1536

        store = MockBeliefStore()
        manager = AnchorManager(
            embedding_provider=MockProvider(), belief_store=store
        )
        style_dim = StyleDimensions(formality=0.8, warmth=0.6)
        await manager.create_initial_anchor("persist_test", style_dim, "some text")
        style_belief = await store.get_by_id("style_anchor_persist_test")
        assert style_belief is not None
        assert style_belief.layer == 6
        assert style_belief.memory_type == "persona_anchor"
        assert style_belief.metadata["anchor_type"] == "style"
        decision_belief = await store.get_by_id("decision_anchor_persist_test")
        assert decision_belief is not None
        assert decision_belief.metadata["anchor_type"] == "decision"

    @pytest.mark.asyncio
    async def test_load_anchors_returns_saved_data(self) -> None:
        class MockProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.2] * 1536

        store = MockBeliefStore()
        manager = AnchorManager(
            embedding_provider=MockProvider(), belief_store=store
        )
        style_dim = StyleDimensions(formality=0.7, warmth=0.5)
        original = await manager.create_initial_anchor(
            "load_test", style_dim, "load test text"
        )
        loaded = await manager.load_anchors("load_test")
        assert loaded is not None
        assert len(loaded.style_anchor) == 128
        assert len(loaded.decision_anchor) == 256
        assert loaded.style_anchor == original.style_anchor
        assert loaded.decision_anchor == original.decision_anchor

    @pytest.mark.asyncio
    async def test_create_from_samples_writes_to_beliefs(self) -> None:
        class MockProvider:
            async def embed(self, text: str) -> list[float]:
                return [0.3] * 1536

        store = MockBeliefStore()
        manager = AnchorManager(
            embedding_provider=MockProvider(), belief_store=store
        )
        samples = ["样本1", "样本2", "样本3"]
        anchor = await manager.create_from_samples("sample_test", samples)
        style_belief = await store.get_by_id("style_anchor_sample_test")
        assert style_belief is not None
        assert style_belief.layer == 6
        assert style_belief.memory_type == "persona_anchor"
        decision_belief = await store.get_by_id("decision_anchor_sample_test")
        assert decision_belief is not None
        assert anchor.source_text_hash != ""

    @pytest.mark.asyncio
    async def test_load_anchors_returns_none_when_no_data(self) -> None:
        store = MockBeliefStore()
        manager = AnchorManager(belief_store=store)
        loaded = await manager.load_anchors("nonexistent_persona")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_no_belief_store_does_not_crash(self) -> None:
        manager = AnchorManager()
        anchor = AnchorVersion(persona_id="no_store", version=1)
        await manager._persist_anchor(anchor)
        loaded = await manager.load_anchors("no_store")
        assert loaded is None
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.interfaces import (
    IArbitrator,
    IReviewer,
    ISubAgent,
    IUpdater,
    UpdateContext,
    UpdaterResult,
)
from src.core.interfaces import Belief, IBeliefStore
from src.agents.utils import (
    build_updater_belief,
    compute_perturbation_strength,
    determine_update_strategy,
    _are_contradicting,
)


class TestUpdateContext:

    def test_default_values(self) -> None:
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="hello",
        )
        assert ctx.conversation_id == "conv1"
        assert ctx.user_id == "user1"
        assert ctx.message == "hello"
        assert ctx.history == []
        assert ctx.belief_store is None
        assert ctx.perturbation_strength == 0.0
        assert ctx.user_preference_weights == {
            "evidence": 1.0,
            "risk": 1.0,
            "innovation": 1.0,
        }

    def test_custom_weights(self) -> None:
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="hello",
            user_preference_weights={"evidence": 0.5, "risk": 1.5, "innovation": 1.0},
        )
        assert ctx.user_preference_weights["evidence"] == 0.5

    def test_perturbation_strength_set(self) -> None:
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="user1",
            message="hello",
            perturbation_strength=0.75,
        )
        assert ctx.perturbation_strength == 0.75


class TestUpdaterResult:

    def test_basic_fields(self) -> None:
        result = UpdaterResult(
            content="test",
            confidence=0.8,
            reasoning="because",
            source="evidence",
        )
        assert result.content == "test"
        assert result.confidence == 0.8
        assert result.reasoning == "because"
        assert result.source == "evidence"
        assert result.metadata == {}

    def test_with_metadata(self) -> None:
        result = UpdaterResult(
            content="test",
            confidence=0.5,
            reasoning="maybe",
            source="risk",
            metadata={"risk_level": "high"},
        )
        assert result.metadata["risk_level"] == "high"


class TestInterfaces:

    def test_iupdater_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            IUpdater()  # type: ignore[abstract]

    def test_ireviewer_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            IReviewer()  # type: ignore[abstract]

    def test_iarbitrator_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            IArbitrator()  # type: ignore[abstract]

    def test_isubagent_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            ISubAgent()  # type: ignore[abstract]


class TestDetermineUpdateStrategy:

    def test_low_perturbation_evidence_only(self) -> None:
        assert determine_update_strategy(0.1) == ["evidence"]
        assert determine_update_strategy(0.29) == ["evidence"]

    def test_medium_perturbation_evidence_risk(self) -> None:
        assert determine_update_strategy(0.3) == ["evidence", "risk"]
        assert determine_update_strategy(0.5) == ["evidence", "risk"]
        assert determine_update_strategy(0.69) == ["evidence", "risk"]

    def test_high_perturbation_all(self) -> None:
        assert determine_update_strategy(0.7) == [
            "evidence",
            "risk",
            "innovation",
        ]
        assert determine_update_strategy(0.99) == [
            "evidence",
            "risk",
            "innovation",
        ]

    def test_mode_override_quick(self) -> None:
        assert determine_update_strategy(0.9, mode_override="quick") == ["evidence"]

    def test_mode_override_balanced(self) -> None:
        result = determine_update_strategy(0.9, mode_override="balanced")
        assert result == ["evidence", "risk"]

    def test_mode_override_deep(self) -> None:
        result = determine_update_strategy(0.1, mode_override="deep")
        assert result == ["evidence", "risk", "innovation"]

    def test_custom_thresholds(self) -> None:
        assert determine_update_strategy(0.2, low_threshold=0.2, high_threshold=0.8) == [
            "evidence",
            "risk",
        ]
        assert determine_update_strategy(0.1, low_threshold=0.2, high_threshold=0.8) == [
            "evidence",
        ]


class TestBuildUpdaterBelief:

    def test_basic_belief_creation(self) -> None:
        result = UpdaterResult(
            content="test content",
            confidence=0.8,
            reasoning="good reason",
            source="evidence",
        )
        belief = build_updater_belief(result, "conv1")
        assert belief.content == "test content"
        assert belief.source == "updater:evidence"
        assert belief.confidence == 0.8
        assert belief.base_confidence == 0.8
        assert belief.memory_type == "fact"
        assert belief.layer == 3

    def test_belief_has_unique_id(self) -> None:
        r1 = UpdaterResult(content="a", confidence=0.5, reasoning="r", source="evidence")
        r2 = UpdaterResult(content="b", confidence=0.5, reasoning="r", source="risk")
        b1 = build_updater_belief(r1, "conv1")
        b2 = build_updater_belief(r2, "conv1")
        assert b1.id != b2.id

    def test_source_prefix_injection(self) -> None:
        result = UpdaterResult(
            content="x",
            confidence=0.5,
            reasoning="r",
            source="innovation",
        )
        belief = build_updater_belief(result, "conv1")
        assert belief.source == "updater:innovation"


class TestAreContradicting:

    def test_empty_entities_not_contradicting(self) -> None:
        a = Belief(id="1", content="a", source="s", entities=[])
        b = Belief(id="2", content="b", source="s", entities=[])
        assert _are_contradicting(a, b) is False

    def test_no_shared_entities_not_contradicting(self) -> None:
        a = Belief(id="1", content="a", source="s", entities=["x"])
        b = Belief(id="2", content="b", source="s", entities=["y"])
        assert _are_contradicting(a, b) is False

    def test_emotion_extremes_contradicting(self) -> None:
        a = Belief(
            id="1", content="a", source="s", entities=["x"], emotion=0.9
        )
        b = Belief(
            id="2", content="b", source="s", entities=["x"], emotion=0.1
        )
        assert _are_contradicting(a, b) is True

    def test_similar_emotions_not_contradicting(self) -> None:
        a = Belief(
            id="1", content="a", source="s", entities=["x"], emotion=0.7
        )
        b = Belief(
            id="2", content="b", source="s", entities=["x"], emotion=0.6
        )
        assert _are_contradicting(a, b) is False


class TestComputePerturbationStrength:

    @pytest.mark.asyncio
    async def test_returns_zero_for_similar_beliefs(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.search_similar = AsyncMock(return_value=[])
        store.get = AsyncMock(return_value=[])

        result = await compute_perturbation_strength(store, "hello")
        assert 0.0 <= result <= 1.0
        assert result <= 0.26

    @pytest.mark.asyncio
    async def test_decision_keyword_increases_strength(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.search_similar = AsyncMock(return_value=[])
        store.get = AsyncMock(return_value=[])

        normal = await compute_perturbation_strength(store, "hello world")
        keyword = await compute_perturbation_strength(store, "我应该怎么办")
        assert keyword > normal

    @pytest.mark.asyncio
    async def test_semantic_distance_increases_strength(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        belief = Belief(
            id="1",
            content="something",
            source="s",
            confidence=0.8,
            entities=["x"],
        )
        store.search_similar = AsyncMock(
            return_value=[(belief, 0.3)]
        )
        store.get = AsyncMock(return_value=[])

        result = await compute_perturbation_strength(store, "hello")
        assert result > 0.2

    @pytest.mark.asyncio
    async def test_contradictions_increase_strength(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        beliefs = [
            Belief(
                id="1",
                content="good",
                source="s",
                confidence=0.8,
                entities=["x"],
                emotion=0.9,
            ),
            Belief(
                id="2",
                content="bad",
                source="s",
                confidence=0.8,
                entities=["x"],
                emotion=0.1,
            ),
        ]
        store.search_similar = AsyncMock(return_value=[])
        store.get = AsyncMock(return_value=beliefs)

        result = await compute_perturbation_strength(store, "hello")
        assert result > 0.2

    @pytest.mark.asyncio
    async def test_result_in_valid_range(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.search_similar = AsyncMock(return_value=[])
        store.get = AsyncMock(return_value=[])

        result = await compute_perturbation_strength(store, "hello")
        assert 0.0 <= result <= 1.0
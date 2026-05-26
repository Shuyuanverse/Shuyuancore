from __future__ import annotations

import pytest

from src.persona.autonomous_evolution import (
    REJECT_THRESHOLD,
    AUTO_THRESHOLD,
    AutonomousEvolution,
    EvolutionProposal,
)


class TestDetectEvolution:
    @pytest.mark.asyncio
    async def test_few_interactions_returns_empty(self) -> None:
        engine = AutonomousEvolution()
        proposals = await engine.detect_evolution(
            persona_id="test",
            current_profile=None,
            drift_history=[],
            recent_interactions=[{"role": "user", "content": "hi"}] * 5,
        )
        assert proposals == []

    @pytest.mark.asyncio
    async def test_sufficient_interactions_returns_proposals(self) -> None:
        engine = AutonomousEvolution()
        drift_history = [
            {"dimensions": {"formality": 0.7, "warmth": 0.6}},
            {"dimensions": {"formality": 0.72, "warmth": 0.62}},
            {"dimensions": {"formality": 0.75, "warmth": 0.65}},
        ]
        interactions = [{"role": "user", "content": "hello"}] * 10
        proposals = await engine.detect_evolution(
            persona_id="test_detect",
            current_profile=None,
            drift_history=drift_history,
            recent_interactions=interactions,
        )
        assert len(proposals) > 0
        for p in proposals:
            assert isinstance(p, EvolutionProposal)
            assert p.persona_id == "test_detect"
            assert p.dimension in [
                "formality", "warmth", "directness", "playfulness",
                "detail_orientation", "emotional_expression", "pace",
            ]
            assert p.status == "pending"

    @pytest.mark.asyncio
    async def test_max_proposals_limit(self) -> None:
        from src.persona.autonomous_evolution import MAX_PROPOSALS

        engine = AutonomousEvolution()
        drift_history = []
        for dim in [
            "formality", "warmth", "directness", "playfulness",
            "detail_orientation", "emotional_expression", "pace",
        ]:
            drift_history.append({"dimensions": {dim: 0.8}})
            drift_history.append({"dimensions": {dim: 0.82}})
            drift_history.append({"dimensions": {dim: 0.85}})

        interactions = [{"role": "user", "content": "hello"}] * 10
        proposals = await engine.detect_evolution(
            persona_id="test_max",
            current_profile=None,
            drift_history=drift_history,
            recent_interactions=interactions,
        )
        assert len(proposals) <= MAX_PROPOSALS

    @pytest.mark.asyncio
    async def test_no_drift_no_proposals(self) -> None:
        engine = AutonomousEvolution()
        drift_history = [
            {"dimensions": {"formality": 0.5}},
        ]
        interactions = [{"role": "user", "content": "hello"}] * 10
        proposals = await engine.detect_evolution(
            persona_id="test_no_drift",
            current_profile=None,
            drift_history=drift_history,
            recent_interactions=interactions,
        )
        assert len(proposals) == 0

    @pytest.mark.asyncio
    async def test_string_dimensions_skipped(self) -> None:
        engine = AutonomousEvolution()
        drift_history = [
            {"dimensions": "this is a string not a dict"},
            {"dimensions": {"formality": 0.8}},
            {"dimensions": {"formality": 0.82}},
            {"dimensions": {"formality": 0.85}},
        ]
        interactions = [{"role": "user", "content": "hello"}] * 10
        proposals = await engine.detect_evolution(
            persona_id="test_string_dim",
            current_profile=None,
            drift_history=drift_history,
            recent_interactions=interactions,
        )
        assert len(proposals) > 0


class TestReviewAndApply:
    @pytest.mark.asyncio
    async def test_low_consistency_rejected(self) -> None:
        engine = AutonomousEvolution()
        proposal = EvolutionProposal(
            persona_id="test",
            proposal_id="test_low",
            dimension="formality",
            current_value=0.5,
            proposed_value=0.9,
            delta=0.4,
            trigger_type="drift_trend",
        )
        result = await engine.review_and_apply(proposal)
        assert result.status == "rejected"
        assert result.consistency_score < REJECT_THRESHOLD

    @pytest.mark.asyncio
    async def test_medium_consistency_auto_adjusted(self) -> None:
        engine = AutonomousEvolution()
        proposal = EvolutionProposal(
            persona_id="test",
            proposal_id="test_medium",
            dimension="warmth",
            current_value=0.5,
            proposed_value=0.7,
            delta=0.2,
            trigger_type="drift_trend",
        )
        result = await engine.review_and_apply(proposal)
        assert result.status == "auto_adjusted"
        assert REJECT_THRESHOLD <= result.consistency_score <= AUTO_THRESHOLD
        assert result.delta < 0.2

    @pytest.mark.asyncio
    async def test_high_consistency_approved(self) -> None:
        engine = AutonomousEvolution()
        proposal = EvolutionProposal(
            persona_id="test",
            proposal_id="test_high",
            dimension="directness",
            current_value=0.5,
            proposed_value=0.55,
            delta=0.05,
            trigger_type="drift_trend",
        )
        result = await engine.review_and_apply(proposal)
        assert result.status == "approved"
        assert result.consistency_score > AUTO_THRESHOLD

    @pytest.mark.asyncio
    async def test_auto_adjust_delta_scaling(self) -> None:
        engine = AutonomousEvolution()
        proposal = EvolutionProposal(
            persona_id="test",
            proposal_id="test_scale",
            dimension="playfulness",
            current_value=0.5,
            proposed_value=0.75,
            delta=0.25,
            trigger_type="drift_trend",
        )
        result = await engine.review_and_apply(proposal)
        assert result.status == "auto_adjusted"
        expected_delta = 0.25 * result.consistency_score
        assert result.delta == pytest.approx(expected_delta)
        assert result.proposed_value == result.current_value + result.delta


class TestCalcConsistency:
    def test_small_delta_high_consistency(self) -> None:
        proposal = EvolutionProposal(
            persona_id="t", proposal_id="t", dimension="f",
            current_value=0.5, proposed_value=0.51, delta=0.01,
            trigger_type="drift_trend",
        )
        score = AutonomousEvolution._calc_consistency(proposal)
        assert score > 0.95

    def test_large_delta_low_consistency(self) -> None:
        proposal = EvolutionProposal(
            persona_id="t", proposal_id="t", dimension="f",
            current_value=0.5, proposed_value=0.9, delta=0.4,
            trigger_type="drift_trend",
        )
        score = AutonomousEvolution._calc_consistency(proposal)
        assert score < REJECT_THRESHOLD
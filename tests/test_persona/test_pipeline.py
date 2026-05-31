from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.perception import PerceptionResult
from src.persona.pipeline import PipelineContext, orchestrate_background
from src.persona.profile import PersonaProfile, StyleDimensions


def _make_profile() -> PersonaProfile:
    return PersonaProfile(
        persona_id="test_pipeline",
        mode="generic",
        style_dimensions=StyleDimensions(),
        style_anchor_vector=[0.5] * 128,
        version=1,
    )


class TestPipelineContext:
    @pytest.mark.asyncio
    async def test_record_drift(self) -> None:
        pctx = PipelineContext()
        entry = {"drift_score": 0.3, "alert_level": "moderate", "persona_id": "test"}
        await pctx.record_drift(entry)
        assert len(pctx.drift_history) == 1
        assert pctx.drift_history[0] == entry

    @pytest.mark.asyncio
    async def test_record_multiple_drifts(self) -> None:
        pctx = PipelineContext()
        for i in range(5):
            await pctx.record_drift({"drift_score": i * 0.1, "alert_level": "slight"})
        assert len(pctx.drift_history) == 5

    @pytest.mark.asyncio
    async def test_get_drift_history_limit(self) -> None:
        pctx = PipelineContext()
        for i in range(100):
            await pctx.record_drift({"drift_score": i * 0.01, "alert_level": "none"})
        history = await pctx.get_drift_history(limit=10)
        assert len(history) == 10

    @pytest.mark.asyncio
    async def test_get_drift_history_returns_latest(self) -> None:
        pctx = PipelineContext()
        for i in range(10):
            await pctx.record_drift({"index": i, "drift_score": i * 0.1})
        history = await pctx.get_drift_history(limit=3)
        assert history[-1]["index"] == 9
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_concurrent_record_safety(self) -> None:
        pctx = PipelineContext()
        async def record_many(n: int) -> None:
            for i in range(n):
                await pctx.record_drift({"drift_score": i * 0.01, "alert_level": "none"})

        await asyncio.gather(record_many(10), record_many(10))
        assert len(pctx.drift_history) == 20


class TestOrchestrateBackground:
    @pytest.mark.asyncio
    async def test_basic_orchestration(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.8)

        drift_store = AsyncMock()
        drift_store.add_drift_record = AsyncMock()

        await orchestrate_background(
            user_message="你好",
            response_text="你好，有什么可以帮您",
            conversation_history=[],
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            drift_store=drift_store,
        )

        drift_store.add_drift_record.assert_called_once()
        assert len(pctx.drift_history) == 1

    @pytest.mark.asyncio
    async def test_orchestration_without_perception(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()

        drift_store = AsyncMock()
        drift_store.add_drift_record = AsyncMock()

        await orchestrate_background(
            user_message="你好",
            response_text="你好",
            conversation_history=[],
            persona_profile=profile,
            perception=None,
            pctx=pctx,
            drift_store=drift_store,
        )

        drift_store.add_drift_record.assert_not_called()
        assert len(pctx.drift_history) == 0

    @pytest.mark.asyncio
    async def test_orchestration_with_evolution(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.9)

        evolution_engine = AsyncMock()
        evolution_engine.detect_evolution.return_value = []
        evolution_engine.review_and_apply = AsyncMock()

        drift_store = AsyncMock()
        drift_store.add_drift_record = AsyncMock()

        history = [{"role": "user", "content": "hi"}] * 10

        await orchestrate_background(
            user_message="hi",
            response_text="hello",
            conversation_history=history,
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            evolution_engine=evolution_engine,
            drift_store=drift_store,
        )

        evolution_engine.detect_evolution.assert_called_once()
        assert len(pctx.drift_history) == 1

    @pytest.mark.asyncio
    async def test_orchestration_without_drift_store(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.9)

        await orchestrate_background(
            user_message="你好",
            response_text="你好",
            conversation_history=[],
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            drift_store=None,
        )

        assert len(pctx.drift_history) == 0

    @pytest.mark.asyncio
    async def test_evolution_triggered_at_multiple_of_10(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.9)

        evolution_engine = AsyncMock()
        evolution_engine.detect_evolution.return_value = [
            MagicMock(proposal_id="p1", status="approved")
        ]
        evolution_engine.review_and_apply = AsyncMock(
            return_value=MagicMock(proposal_id="p1", status="approved")
        )

        drift_store = AsyncMock()
        drift_store.add_drift_record = AsyncMock()

        history = [{"role": "user", "content": "hi"}] * 20

        await orchestrate_background(
            user_message="hi",
            response_text="hello",
            conversation_history=history,
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            evolution_engine=evolution_engine,
            drift_store=drift_store,
        )

        evolution_engine.detect_evolution.assert_called_once()
        evolution_engine.review_and_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_evolution_exception_handled(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.9)

        evolution_engine = MagicMock()
        evolution_engine.detect_evolution = AsyncMock(side_effect=RuntimeError("evolution failed"))

        drift_store = AsyncMock()
        drift_store.add_drift_record = AsyncMock()

        history = [{"role": "user", "content": "hi"}] * 10

        await orchestrate_background(
            user_message="hi",
            response_text="hello",
            conversation_history=history,
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            evolution_engine=evolution_engine,
            drift_store=drift_store,
        )

        drift_store.add_drift_record.assert_called_once()
        assert len(pctx.drift_history) == 1

    @pytest.mark.asyncio
    async def test_drift_store_exception_handled(self) -> None:
        pctx = PipelineContext()
        profile = _make_profile()
        perception = PerceptionResult(patience_level=0.9)

        drift_store = MagicMock()
        drift_store.add_drift_record = AsyncMock(side_effect=RuntimeError("store failed"))

        await orchestrate_background(
            user_message="你好",
            response_text="你好",
            conversation_history=[],
            persona_profile=profile,
            perception=perception,
            pctx=pctx,
            drift_store=drift_store,
        )

        assert len(pctx.drift_history) == 1


import asyncio
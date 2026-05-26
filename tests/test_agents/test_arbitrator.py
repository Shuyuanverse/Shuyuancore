from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.arbitrator import (
    Arbitrator,
    _detect_conflict,
    _content_similarity,
    _weighted_fusion,
    _format_single_result,
    _format_structured_data,
    _source_label,
)
from src.agents.interfaces import UpdateContext, UpdaterResult
from src.models.interfaces import ChatResult, IModelProvider


def _make_ctx(
    message: str = "hello",
    weights: dict[str, float] | None = None,
) -> UpdateContext:
    ctx = UpdateContext(
        conversation_id="conv1",
        user_id="user1",
        message=message,
    )
    if weights:
        ctx.user_preference_weights = weights
    return ctx


def _make_provider(response_content: str) -> IModelProvider:
    provider = MagicMock(spec=IModelProvider)
    provider.chat = AsyncMock(
        return_value=ChatResult(content=response_content, model_used="test")
    )
    return provider


class TestSourceLabel:

    def test_known_sources(self) -> None:
        assert _source_label("evidence") == "证据"
        assert _source_label("risk") == "风险"
        assert _source_label("innovation") == "创新"

    def test_unknown_source(self) -> None:
        assert _source_label("unknown") == "unknown"


class TestContentSimilarity:

    def test_identical(self) -> None:
        assert _content_similarity("完全相同的内容", "完全相同的内容") > 0.9

    def test_completely_different(self) -> None:
        sim = _content_similarity("方案A非常优秀", "风险极高不推荐")
        assert sim < 0.5

    def test_empty_strings(self) -> None:
        assert _content_similarity("", "") == 1.0
        assert _content_similarity("a", "") == 1.0


class TestDetectConflict:

    def test_no_conflict_high_similarity(self) -> None:
        results = [
            UpdaterResult(content="推荐方案A", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="建议方案A", confidence=0.7, reasoning="r", source="risk"),
        ]
        assert _detect_conflict(results) is False

    def test_conflict_low_similarity(self) -> None:
        results = [
            UpdaterResult(content="推荐方案A", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="风险极高不推荐", confidence=0.7, reasoning="r", source="risk"),
        ]
        assert _detect_conflict(results) is True

    def test_conflict_confidence_gap(self) -> None:
        results = [
            UpdaterResult(content="相似内容", confidence=0.9, reasoning="r", source="evidence"),
            UpdaterResult(content="相似内容", confidence=0.3, reasoning="r", source="risk"),
        ]
        assert _detect_conflict(results) is True

    def test_single_result_no_conflict(self) -> None:
        results = [
            UpdaterResult(content="x", confidence=0.5, reasoning="r", source="evidence"),
        ]
        assert _detect_conflict(results) is False


class TestWeightedFusion:

    def test_custom_weights(self) -> None:
        results = [
            UpdaterResult(content="a", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="b", confidence=0.8, reasoning="r", source="risk"),
        ]
        fused = _weighted_fusion(results, {"evidence": 0.5, "risk": 1.0})
        assert fused[0].confidence == 0.4
        assert fused[1].confidence == 0.8

    def test_default_weight_for_missing(self) -> None:
        results = [
            UpdaterResult(content="a", confidence=0.8, reasoning="r", source="evidence"),
        ]
        fused = _weighted_fusion(results, {})
        assert fused[0].confidence == 0.8


class TestFormatSingleResult:

    def test_basic_format(self) -> None:
        result = UpdaterResult(
            content="建议A",
            confidence=0.8,
            reasoning="r",
            source="evidence",
        )
        output = _format_single_result(result)
        assert "证据" in output
        assert "建议A" in output
        assert "0.80" in output


class TestFormatStructuredData:

    def test_basic_format(self) -> None:
        results = [
            UpdaterResult(content="赞成", confidence=0.8, reasoning="数据好", source="evidence"),
            UpdaterResult(content="反对", confidence=0.6, reasoning="风险高", source="risk"),
        ]
        weights = {"evidence": 1.0, "risk": 1.0}
        output = _format_structured_data(results, weights)
        assert "证据视角" in output
        assert "风险视角" in output
        assert "综合" in output
        assert "数据好" in output
        assert "风险高" in output


class TestArbitrator:

    @pytest.mark.asyncio
    async def test_single_result_no_fusion(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        arb = Arbitrator(provider)
        ctx = _make_ctx("question")
        results = [
            UpdaterResult(content="答案A", confidence=0.8, reasoning="r", source="evidence"),
        ]
        output = await arb.arbitrate(ctx, results)
        assert "证据视角" in output
        assert "答案A" in output
        provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_conflict_uses_best(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        arb = Arbitrator(provider)
        ctx = _make_ctx("question")
        results = [
            UpdaterResult(content="推荐A", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="也推荐A", confidence=0.7, reasoning="r", source="risk"),
        ]
        output = await arb.arbitrate(ctx, results)
        assert "证据视角" in output
        assert "0.80" in output

    @pytest.mark.asyncio
    async def test_conflict_triggers_polish(self) -> None:
        provider = _make_provider("融合后的最终回复：综合建议采用方案B")
        arb = Arbitrator(provider)
        ctx = _make_ctx("我该怎么办")
        results = [
            UpdaterResult(content="推荐A", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="风险极大不推荐", confidence=0.7, reasoning="r", source="risk"),
        ]
        output = await arb.arbitrate(ctx, results)
        assert "方案B" in output or "融合" in output

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        arb = Arbitrator(provider)
        ctx = _make_ctx("question")
        output = await arb.arbitrate(ctx, [])
        assert "无可用" in output

    @pytest.mark.asyncio
    async def test_polish_failure_fallback(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(side_effect=RuntimeError("timeout"))
        arb = Arbitrator(provider)
        ctx = _make_ctx("question")
        results = [
            UpdaterResult(content="推荐A", confidence=0.8, reasoning="r", source="evidence"),
            UpdaterResult(content="风险大", confidence=0.7, reasoning="r", source="risk"),
        ]
        output = await arb.arbitrate(ctx, results)
        assert "证据" in output
        assert "综合" in output
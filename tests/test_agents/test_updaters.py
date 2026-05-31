from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.interfaces import UpdateContext, UpdaterResult
from src.agents.updater_evidence import EvidenceUpdater, _parse_updater_json
from src.agents.updater_risk import RiskUpdater
from src.agents.updater_innovation import InnovationUpdater
from src.core.interfaces import Belief, IBeliefStore
from src.models.interfaces import ChatResult, IModelProvider


def _make_ctx(message: str = "hello") -> UpdateContext:
    store = MagicMock(spec=IBeliefStore)
    store.get = AsyncMock(return_value=[])
    return UpdateContext(
        conversation_id="conv1",
        user_id="user1",
        message=message,
        belief_store=store,
    )


def _make_provider(response_content: str) -> IModelProvider:
    provider = MagicMock(spec=IModelProvider)
    provider.chat = AsyncMock(
        return_value=ChatResult(content=response_content, model_used="test")
    )
    return provider


class TestParseUpdaterJson:

    def test_valid_json(self) -> None:
        raw = '{"content": "建议采用方案A", "confidence": 0.8, "reasoning": "数据支持"}'
        result = _parse_updater_json(raw, "evidence")
        assert result.source == "evidence"
        assert result.content == "建议采用方案A"
        assert result.confidence == 0.8
        assert result.reasoning == "数据支持"

    def test_json_with_surrounding_text(self) -> None:
        raw = '一些前言{"content": "test", "confidence": 0.5, "reasoning": "r"}后续'
        result = _parse_updater_json(raw, "risk")
        assert result.content == "test"

    def test_invalid_json_fallback(self) -> None:
        raw = "只是一段纯文本"
        result = _parse_updater_json(raw, "innovation")
        assert result.content == "只是一段纯文本"
        assert result.confidence == 0.5
        assert "JSON 解析失败" in result.reasoning

    def test_confidence_clamped(self) -> None:
        raw = '{"content": "x", "confidence": 2.5, "reasoning": "r"}'
        result = _parse_updater_json(raw, "evidence")
        assert result.confidence == 1.0

    def test_missing_fields(self) -> None:
        raw = '{"content": "x"}'
        result = _parse_updater_json(raw, "evidence")
        assert result.content == "x"
        assert result.confidence == 0.5


class TestEvidenceUpdater:

    @pytest.mark.asyncio
    async def test_basic_update(self) -> None:
        provider = _make_provider(
            '{"content": "建议A", "confidence": 0.7, "reasoning": "有充足证据"}'
        )
        updater = EvidenceUpdater(provider)
        ctx = _make_ctx("我应该选哪个方案？")
        result = await updater.update(ctx)
        assert isinstance(result, UpdaterResult)
        assert result.source == "evidence"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(side_effect=RuntimeError("api down"))
        updater = EvidenceUpdater(provider)
        ctx = _make_ctx("hello")
        result = await updater.update(ctx)
        assert result.source == "evidence"
        assert "LLM 调用失败" in result.content
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_belief_context_included(self) -> None:
        store = MagicMock(spec=IBeliefStore)
        store.get = AsyncMock(
            return_value=[
                Belief(
                    id="b1",
                    content="用户喜欢 Python",
                    source="user",
                    confidence=0.9,
                )
            ]
        )
        provider = _make_provider(
            '{"content": "推荐Python方案", "confidence": 0.8, "reasoning": "用户偏好"}'
        )
        updater = EvidenceUpdater(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="u1",
            message="用什么语言？",
            belief_store=store,
        )
        result = await updater.update(ctx)
        assert isinstance(result, UpdaterResult)

    @pytest.mark.asyncio
    async def test_no_belief_store(self) -> None:
        provider = _make_provider(
            '{"content": "ok", "confidence": 0.5, "reasoning": "基本判断"}'
        )
        updater = EvidenceUpdater(provider)
        ctx = UpdateContext(
            conversation_id="conv1",
            user_id="u1",
            message="hello",
        )
        result = await updater.update(ctx)
        assert result.source == "evidence"


class TestRiskUpdater:

    @pytest.mark.asyncio
    async def test_basic_risk_analysis(self) -> None:
        provider = _make_provider(
            '{"content": "存在性能风险", "confidence": 0.6, "reasoning": "高并发场景"}'
        )
        updater = RiskUpdater(provider)
        ctx = _make_ctx("我要部署一个新服务")
        result = await updater.update(ctx)
        assert result.source == "risk"
        assert "性能风险" in result.content

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(side_effect=RuntimeError("timeout"))
        updater = RiskUpdater(provider)
        ctx = _make_ctx("hello")
        result = await updater.update(ctx)
        assert result.source == "risk"
        assert "LLM 调用失败" in result.content


class TestInnovationUpdater:

    @pytest.mark.asyncio
    async def test_basic_innovation(self) -> None:
        provider = _make_provider(
            '{"content": "试试微服务架构", "confidence": 0.5, "reasoning": "新思路"}'
        )
        updater = InnovationUpdater(provider)
        ctx = _make_ctx("我们的单体应用太慢了")
        result = await updater.update(ctx)
        assert result.source == "innovation"
        assert "微服务" in result.content

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(side_effect=RuntimeError("timeout"))
        updater = InnovationUpdater(provider)
        ctx = _make_ctx("hello")
        result = await updater.update(ctx)
        assert result.source == "innovation"
        assert "LLM 调用失败" in result.content

    @pytest.mark.asyncio
    async def test_higher_temperature(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(
            return_value=ChatResult(
                content='{"content": "方案B", "confidence": 0.4, "reasoning": "创新"}',
                model_used="test",
            )
        )
        updater = InnovationUpdater(provider)
        ctx = _make_ctx("test")
        await updater.update(ctx)
        call_kwargs = provider.chat.call_args[1]
        assert call_kwargs["temperature"] == 0.7
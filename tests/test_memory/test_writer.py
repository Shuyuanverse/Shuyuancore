# ruff: noqa: N802
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.memory.writer import (
    AiInferenceWriter,
    CompositeBeliefDetector,
    ManualMemoryWriter,
    RuleBasedWriter,
)


@pytest.fixture
def mock_store() -> AsyncMock:
    store = AsyncMock()
    store.add = AsyncMock(return_value="new_id")
    return store


@pytest.fixture
def mock_entity_extractor() -> MagicMock:
    ext = MagicMock()
    ext.extract.return_value = ["entity"]
    return ext


@pytest.fixture
def mock_emotion_analyzer() -> MagicMock:
    ana = MagicMock()
    ana.analyze.return_value = 0.6
    return ana


class TestRuleBasedWriter:

    @pytest.mark.asyncio
    async def test_identity_pattern_我叫(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = RuleBasedWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("我叫小明", 1000)
        assert len(beliefs) == 1
        assert beliefs[0].memory_type == "identity"
        assert beliefs[0].layer == 1
        assert "小明" in beliefs[0].content
        mock_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preference_pattern_我喜欢(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = RuleBasedWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("我喜欢吃苹果和香蕉", 1000)
        assert len(beliefs) == 1
        assert beliefs[0].memory_type == "preference"
        assert beliefs[0].layer == 1

    @pytest.mark.asyncio
    async def test_preference_pattern_我讨厌(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = RuleBasedWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("我讨厌下雨天", 1000)
        assert len(beliefs) == 1
        assert beliefs[0].memory_type == "preference"

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = RuleBasedWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("今天天气真好", 1000)
        assert len(beliefs) == 0


class TestManualMemoryWriter:

    @pytest.mark.asyncio
    async def test_manual_pattern_记住(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = ManualMemoryWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("记住: 项目名称, 截止日期, 团队成员", 1000)
        assert len(beliefs) == 3
        assert all(b.memory_type == "fact" for b in beliefs)
        assert all(b.layer == 3 for b in beliefs)
        assert mock_store.add.await_count == 3

    @pytest.mark.asyncio
    async def test_non_manual_text_returns_empty(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = ManualMemoryWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("这只是普通对话", 1000)
        assert len(beliefs) == 0

    @pytest.mark.asyncio
    async def test_manual_pattern_with_chinese_colon(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = ManualMemoryWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        beliefs = await writer.process("记住：苹果，香蕉，橘子", 1000)
        assert len(beliefs) == 3


class TestAiInferenceWriter:

    @pytest.mark.asyncio
    async def test_importance_above_threshold_creates_belief(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = AiInferenceWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        writer._threshold = 0.5
        result = await writer.process_llm_output(
            "用户是一名资深Python工程师", importance=0.8, timestamp_ms=1000
        )
        assert result is not None
        assert result.content == "用户是一名资深Python工程师"
        assert result.confidence == 0.8
        mock_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_importance_below_threshold_returns_none(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = AiInferenceWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        writer._threshold = 0.5
        result = await writer.process_llm_output(
            "用户说了句普通的话", importance=0.3, timestamp_ms=1000
        )
        assert result is None
        mock_store.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_metadata(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        writer = AiInferenceWriter(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        writer._threshold = 0.5
        result = await writer.process_llm_output(
            "重要信息",
            importance=0.9,
            timestamp_ms=1000,
            metadata={"source": "analysis", "topic": "career"},
        )
        assert result is not None
        assert result.metadata["source"] == "analysis"
        assert result.metadata["topic"] == "career"


class TestCompositeBeliefDetector:

    @pytest.mark.asyncio
    async def test_single_turn_returns_empty(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        detector = CompositeBeliefDetector(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        detector._min_rounds = 3
        turns = [{"content": "你好", "role": "user"}]
        beliefs = await detector.process_multi_turn(turns, 1000)
        assert len(beliefs) == 0

    @pytest.mark.asyncio
    async def test_composite_detector_multi_turn_creates_composite(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = [
            "Python", "编程", "Docker", "Kubernetes", "数据", "学习",
        ]
        mock_emotion_analyzer.analyze.return_value = 0.6

        detector = CompositeBeliefDetector(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv_c",
        )
        detector._min_rounds = 3
        turns = [
            {
                "content": "我想系统学习Python编程语言和机器学习框架"
                "以及深度学习、自然语言处理和计算机视觉",
                "role": "user",
            },
            {
                "content": "Python在数据科学和Web开发中都很流行"
                "在人工智能领域应用广泛且生态完善工具链丰富",
                "role": "assistant",
            },
            {
                "content": "我还想深入了解Docker容器和Kuberentes编排"
                "以及搭建持续集成持续部署的自动化流水线",
                "role": "user",
            },
        ]
        beliefs = await detector.process_multi_turn(turns, 1000)
        assert len(beliefs) == 1
        assert beliefs[0].is_composite is True
        assert beliefs[0].layer == 3
        mock_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multi_turn_short_text_returns_empty(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = ["Python"]

        detector = CompositeBeliefDetector(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        detector._min_rounds = 3
        turns = [
            {"content": "好", "role": "user"},
            {"content": "行", "role": "assistant"},
            {"content": "嗯", "role": "user"},
        ]
        beliefs = await detector.process_multi_turn(turns, 1000)
        assert len(beliefs) == 0

    @pytest.mark.asyncio
    async def test_multi_turn_few_entities_returns_empty(
        self,
        mock_store: AsyncMock,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = ["是"]

        detector = CompositeBeliefDetector(
            store=mock_store,
            entity_extractor=mock_entity_extractor,
            emotion_analyzer=mock_emotion_analyzer,
            conversation_id="conv1",
        )
        detector._min_rounds = 3
        turns = [
            {"content": "是的我觉得也是这样的对吧", "role": "user"},
            {"content": "没错确实如此我也是这么想的", "role": "assistant"},
            {"content": "好的那我们就这样决定吧", "role": "user"},
        ]
        beliefs = await detector.process_multi_turn(turns, 1000)
        assert len(beliefs) == 0

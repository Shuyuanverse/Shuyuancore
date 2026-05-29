# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""预测式建模集成单元测试。"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.config import PredictionConfig, Settings
from src.core.agent import Agent
from src.core.interfaces import IBeliefStore, IReader
from src.models.interfaces import IModelProvider
from src.memory.relational import RelationalMemory


class MockBeliefStore(IBeliefStore):
    """模拟信念存储用于测试。"""

    def __init__(self) -> None:
        self._beliefs: dict[str, list] = {}

    async def add(self, conversation_id: str, belief) -> str:
        if conversation_id not in self._beliefs:
            self._beliefs[conversation_id] = []
        self._beliefs[conversation_id].append(belief)
        return belief.id

    async def get(self, conversation_id: str, limit: int = 50) -> list:
        return self._beliefs.get(conversation_id, [])[:limit]

    async def get_by_id(self, belief_id: str):
        return None

    async def update(self, belief) -> None:
        pass

    async def clear(self, conversation_id: str) -> None:
        if conversation_id in self._beliefs:
            del self._beliefs[conversation_id]

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        pass

    async def search_similar(self, query: str, top_k: int = 10, min_confidence: float = 0.1) -> list:
        return []

    async def propagate_confidence(self, belief_id: str, delta: float, visited: set[str] | None = None) -> None:
        pass

    async def get_similar_task_count(
        self,
        query: str,
        days: int = 7,
        similarity_threshold: float = 0.8,
    ) -> int:
        return 0

    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        pass


@pytest_asyncio.fixture
async def agent():
    """创建 Agent 测试夹具。"""
    model_provider = MagicMock(spec=IModelProvider)
    belief_store = MockBeliefStore()
    reader = MagicMock(spec=IReader)

    with patch("src.evolution.module_manager.get_model_provider", return_value=model_provider):
        agent = Agent(
            model_provider=model_provider,
            belief_store=belief_store,
            reader=reader,
        )

    # 覆盖为测试配置
    agent._settings = Settings(
        prediction=PredictionConfig(
            enable_proactive=True,
            idle_timeout_seconds=1,
            confidence_threshold=0.7,
            max_idle_checks_per_conversation=3,
        ),
    )

    return agent


@pytest.mark.asyncio
async def test_prediction_config_loading() -> None:
    """测试配置加载和开关是否生效。"""
    settings = Settings(
        prediction=PredictionConfig(
            enable_proactive=False,
            idle_timeout_seconds=30,
            confidence_threshold=0.7,
            max_idle_checks_per_conversation=3,
        )
    )
    
    assert settings.prediction.enable_proactive is False
    assert settings.prediction.idle_timeout_seconds == 30
    assert settings.prediction.confidence_threshold == 0.7
    assert settings.prediction.max_idle_checks_per_conversation == 3


@pytest.mark.asyncio
async def test_idle_monitor_calls_prediction(agent: Agent) -> None:
    """测试空闲监控任务在超时后是否调用预测。"""
    # Mock user_model.predict_next
    mock_prediction = {
        "predicted_action": "continue_deep_exploration",
        "confidence": 0.85,
        "suggested_response": "我们继续讨论这个话题吗？",
    }
    
    with patch.object(agent.user_model, 'predict_next', new=AsyncMock(return_value=mock_prediction)):
        with patch.object(agent, '_send_proactive_prompt', new=AsyncMock()) as mock_send:
            # 设置过去的时间
            agent._last_activity_time = time.time() - 2
            agent._current_conversation_id = "test_conv"
            
            # 启动监控任务
            agent._idle_monitor_task = asyncio.create_task(agent._idle_monitor())
            
            # 等待超时 + 额外时间
            await asyncio.sleep(1.5)
            
            # 验证调用了预测和发送
            mock_send.assert_called()
            
            # 清理
            agent._idle_monitor_task.cancel()
            try:
                await agent._idle_monitor_task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_proactive_prompt_sending(agent: Agent) -> None:
    """测试主动提醒发送。"""
    prediction = {
        "predicted_action": "simplify_and_clarify",
        "confidence": 0.8,
        "suggested_response": "需要我进一步解释吗？",
    }
    
    with patch.object(agent, '_is_cli', True):
        with patch('builtins.print') as mock_print:
            await agent._send_proactive_prompt(prediction)
            mock_print.assert_called()
            call_args = str(mock_print.call_args)
            assert "主动提醒" in call_args
            assert "需要我进一步解释吗？" in call_args


@pytest.mark.asyncio
async def test_max_idle_checks_limit(agent: Agent) -> None:
    """测试最大提醒次数限制。"""
    agent._proactive_count = 3  # 已达到最大次数
    
    mock_prediction = {
        "predicted_action": "test",
        "confidence": 0.9,
        "suggested_response": "test",
    }
    
    with patch.object(agent.user_model, 'predict_next', new=AsyncMock(return_value=mock_prediction)):
        with patch.object(agent, '_send_proactive_prompt', new=AsyncMock()) as mock_send:
            await agent._idle_monitor()
            # 不应调用发送，因为已达到最大次数
            mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_enable_proactive_false_no_prompt(agent: Agent) -> None:
    """测试 enable_proactive=False 时无提醒。"""
    agent._settings.prediction.enable_proactive = False
    
    with patch.object(agent.user_model, 'predict_next', new=AsyncMock()) as mock_predict:
        await agent._idle_monitor()
        # 不应调用预测
        mock_predict.assert_not_called()


@pytest.mark.asyncio
async def test_confidence_threshold_filter(agent: Agent) -> None:
    """测试置信度阈值过滤。"""
    # 低于阈值的预测
    low_confidence_prediction = {
        "predicted_action": "test",
        "confidence": 0.5,  # 低于 0.7 阈值
        "suggested_response": "test",
    }
    
    with patch.object(agent.user_model, 'predict_next', new=AsyncMock(return_value=low_confidence_prediction)):
        with patch.object(agent, '_send_proactive_prompt', new=AsyncMock()) as mock_send:
            agent._last_activity_time = time.time() - 2
            agent._current_conversation_id = "test"
            
            agent._idle_monitor_task = asyncio.create_task(agent._idle_monitor())
            await asyncio.sleep(1.5)
            
            # 不应发送低置信度提醒
            mock_send.assert_not_called()
            
            agent._idle_monitor_task.cancel()
            try:
                await agent._idle_monitor_task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_proactive_queue_put(agent: Agent) -> None:
    """测试提醒消息放入队列。"""
    prediction = {
        "predicted_action": "test_action",
        "confidence": 0.85,
        "suggested_response": "test_response",
    }
    
    with patch.object(agent.user_model, 'predict_next', new=AsyncMock(return_value=prediction)):
        agent._last_activity_time = time.time() - 2
        agent._current_conversation_id = "test"
        
        agent._idle_monitor_task = asyncio.create_task(agent._idle_monitor())
        await asyncio.sleep(1.5)
        
        # 从队列获取消息
        try:
            msg = await asyncio.wait_for(agent._proactive_queue.get(), timeout=2)
            assert msg["predicted_action"] == "test_action"
            assert msg["confidence"] == 0.85
        except asyncio.TimeoutError:
            pytest.fail("Queue should have received a message")
        
        agent._idle_monitor_task.cancel()
        try:
            await agent._idle_monitor_task
        except asyncio.CancelledError:
            pass

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""决策 Agent — 生成初始回复。

包含：
- DecisionConfig：决策配置
- DecisionContext：决策上下文
- DecisionOutput：决策输出
- DecisionAgent：决策 Agent
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_agent import AgentConfig, BaseAgent
from .agent_protocol import AgentMessage, MessageType, Priority
from src.persona.inner_reaction.perception import PerceptionResult

logger = logging.getLogger(__name__)


@dataclass
class DecisionConfig:
    """决策配置

    Attributes:
        temperature: 温度参数
        max_tokens: 最大 token 数
        enable_rag: 是否启用 RAG
        enable_memory: 是否启用记忆
        style_constraint_strength: 风格约束强度
    """

    temperature: float = 0.7
    max_tokens: int = 500
    enable_rag: bool = True
    enable_memory: bool = True
    style_constraint_strength: float = 0.5


@dataclass
class DecisionContext:
    """决策上下文

    Attributes:
        user_message: 用户消息
        persona_id: 人格 ID
        style_dimensions: 风格维度
        anchor_vector: 锚点向量
        conversation_history: 对话历史
        perception_result: 感知结果
        inner_reaction: 内心反应
    """

    user_message: str
    persona_id: str
    style_dimensions: Dict[str, Any]
    anchor_vector: Optional[List[float]] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    perception_result: Optional[PerceptionResult] = None
    inner_reaction: Optional[str] = None


@dataclass
class DecisionOutput:
    """决策输出

    Attributes:
        response: 回复文本
        confidence: 置信度
        style_alignment: 风格对齐度
        used_catchphrases: 使用的口头禅
        metadata: 元数据
    """

    response: str
    confidence: float
    style_alignment: float
    used_catchphrases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "response": self.response,
            "confidence": self.confidence,
            "style_alignment": self.style_alignment,
            "used_catchphrases": self.used_catchphrases,
            "metadata": self.metadata,
        }


class DecisionAgent(BaseAgent):
    """决策 Agent — 生成初始回复

    处理流程：
    1. 构建完整 prompt：
       - system_prompt：人格设定 + 风格约束 + 内心反应
       - RAG 检索结果（如启用）
       - 记忆召回（如启用）
    2. 调用 LLM 生成回复
    3. 评估风格对齐度
    4. 返回 DecisionOutput
    """

    def __init__(
        self,
        config: Optional[DecisionConfig] = None,
        agent_config: Optional[AgentConfig] = None,
    ):
        """初始化决策 Agent

        Args:
            config: 决策配置
            agent_config: Agent 配置
        """
        if agent_config is None:
            agent_config = AgentConfig(
                agent_id="decision_agent_001",
                agent_type="decision",
            )

        super().__init__(agent_config)

        self.config = config or DecisionConfig()
        logger.info("[decision] 决策 Agent 初始化完成，配置：%s", self.config)

    async def process(self, message: AgentMessage) -> AgentMessage:
        """处理消息

        Args:
            message: 输入消息

        Returns:
            AgentMessage: 输出消息
        """
        try:
            # 解析输入
            context = self._parse_message(message)

            # Step 1: 构建完整 prompt
            system_prompt = self._build_system_prompt(context)

            # Step 2: 调用 LLM 生成回复（简化实现，返回占位文本）
            response_text = await self._call_llm(
                system_prompt=system_prompt,
                user_message=context.user_message,
            )

            # Step 3: 评估风格对齐度
            style_alignment = self._evaluate_style_alignment(
                response_text,
                context.style_dimensions,
            )

            # Step 4: 提取口头禅
            catchphrases = self._extract_catchphrases(response_text)

            # 构建输出
            output = DecisionOutput(
                response=response_text,
                confidence=0.8,  # 简化实现
                style_alignment=style_alignment,
                used_catchphrases=catchphrases,
                metadata={
                    "context": context.to_dict() if hasattr(context, "to_dict") else {},
                    "config": self.config.__dict__,
                },
            )

            # 构建响应消息
            response_message = AgentMessage(
                message_type=MessageType.RESPONSE,
                sender=self.config.agent_id,
                receiver=message.sender,
                content=output,
                priority=message.priority,
                parent_id=message.message_id,
            )

            logger.info(
                "[decision] 处理完成：response_length=%d, style_alignment=%.2f",
                len(response_text),
                style_alignment,
            )

            return response_message

        except Exception as e:
            logger.exception("[decision] 处理失败：%s", e)
            raise

    def _parse_message(self, message: AgentMessage) -> DecisionContext:
        """解析消息为决策上下文

        Args:
            message: 输入消息

        Returns:
            DecisionContext: 决策上下文
        """
        content = message.content

        if isinstance(content, DecisionContext):
            return content

        # 从字典创建
        return DecisionContext(
            user_message=content.get("user_message", ""),
            persona_id=content.get("persona_id", ""),
            style_dimensions=content.get("style_dimensions", {}),
            anchor_vector=content.get("anchor_vector"),
            conversation_history=content.get("conversation_history", []),
            perception_result=content.get("perception_result"),
            inner_reaction=content.get("inner_reaction"),
        )

    def _build_system_prompt(self, context: DecisionContext) -> str:
        """构建系统提示词

        Args:
            context: 决策上下文

        Returns:
            str: 系统提示词
        """
        lines = [
            "你是一个人格化助手，请遵循以下设定：",
            "",
            f"人格 ID: {context.persona_id}",
            "",
            "风格约束：",
        ]

        # 添加风格维度
        for key, value in context.style_dimensions.items():
            lines.append(f"- {key}: {value}")

        # 添加内心反应
        if context.inner_reaction:
            lines.append("")
            lines.append("内心状态：")
            lines.append(context.inner_reaction)

        # 添加 RAG 结果
        if self.config.enable_rag:
            lines.append("")
            lines.append("RAG 检索结果：（暂无）")

        # 添加记忆召回
        if self.config.enable_memory:
            lines.append("")
            lines.append("记忆召回：（暂无）")

        # 添加风格约束强度
        lines.append("")
        lines.append(f"风格约束强度：{self.config.style_constraint_strength}")

        return "\n".join(lines)

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
    ) -> str:
        """调用 LLM 生成回复

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Returns:
            str: LLM 回复

        简化实现：返回占位文本
        实际实现应调用 LLM API
        """
        # TODO: 实现真实的 LLM 调用
        # 目前返回占位文本
        return f"【决策 Agent 回复】收到：{user_message[:50]}..."

    def _evaluate_style_alignment(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
    ) -> float:
        """评估风格对齐度

        Args:
            response: 回复文本
            style_dimensions: 风格维度

        Returns:
            float: 对齐度 0-1

        简化实现：返回固定值
        实际实现应基于风格维度计算
        """
        # TODO: 实现真实的风格对齐度评估
        return 0.85

    def _extract_catchphrases(self, response: str) -> List[str]:
        """提取口头禅

        Args:
            response: 回复文本

        Returns:
            List[str]: 口头禅列表
        """
        # 简化实现：返回空列表
        return []

    def generate_response(
        self,
        context: DecisionContext,
    ) -> DecisionOutput:
        """生成回复（同步接口）

        Args:
            context: 决策上下文

        Returns:
            DecisionOutput: 决策输出
        """
        import asyncio

        # 构建消息
        message = AgentMessage(
            message_type=MessageType.REQUEST,
            sender="external",
            receiver=self.config.agent_id,
            content=context,
        )

        # 同步调用异步方法
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中创建新任务
                task = loop.create_task(self.process(message))
                # 简化处理：不等待
                return DecisionOutput(
                    response="异步处理中...",
                    confidence=0.0,
                    style_alignment=0.0,
                )
            else:
                response_message = loop.run_until_complete(self.process(message))
                return response_message.content
        except RuntimeError:
            # 无事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response_message = loop.run_until_complete(self.process(message))
            loop.close()
            return response_message.content

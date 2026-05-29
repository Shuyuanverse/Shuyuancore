# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""审视 Agent — 4 维度冲突检测。

包含：
- ConflictLevel：冲突级别
- ConflictDetectionResult：冲突检测结果
- ReviewAgentContextExtension：语境理解扩展
- ReviewAgent：审视 Agent
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .agent_protocol import AgentMessage, MessageType
from .base_agent import AgentConfig, BaseAgent

logger = logging.getLogger(__name__)


class ConflictLevel(Enum):
    """冲突级别"""

    NONE = "none"  # 无冲突
    TOLERABLE = "tolerable"  # 可容忍
    NEED_INTERVENTION = "need_intervention"  # 需要干预
    SEVERE = "severe"  # 严重冲突


@dataclass
class ConflictDetectionResult:
    """冲突检测结果

    Attributes:
        conflict_score: 冲突分数 0-1
        conflict_level: 冲突级别
        conflict_type: 冲突类型（lexical/syntactic/semantic/tonal）
        details: 详细信息
    """

    conflict_score: float = 0.0
    conflict_level: ConflictLevel = ConflictLevel.NONE
    conflict_type: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "conflict_score": self.conflict_score,
            "conflict_level": self.conflict_level.value,
            "conflict_type": self.conflict_type,
            "details": self.details,
        }


class ReviewAgentContextExtension:
    """语境理解扩展

    基于感知结果（氛围 + 情绪 + 意图）扩展审视上下文
    判定逻辑：
    - 氛围=紧急 + 冲突=TOLERABLE → pass（紧急情况下容忍轻微偏差）
    - 情绪=friendly + 冲突=TOLERABLE → pass（友好对话中容忍偏差）
    - 氛围=紧张 + 冲突=NEED_INTERVENTION → block（紧张时严格把关）
    - 意图=defend_identity + 冲突=NEED_INTERVENTION → review（身份相关需重新审视）

    输出：context_aware_judge: "pass" / "block" / "review"
    """

    def __init__(self):
        """初始化语境理解扩展"""
        logger.info("[review_context] 语境理解扩展初始化完成")

    def extend(
        self,
        conflict_result: ConflictDetectionResult,
        atmosphere: str = "daily",
        emotion: str = "neutral",
        intent: Optional[str] = None,
    ) -> str:
        """扩展审视上下文

        Args:
            conflict_result: 冲突检测结果
            atmosphere: 氛围
            emotion: 情绪
            intent: 意图

        Returns:
            str: 语境感知判决（pass/block/review）
        """
        # 默认判决
        if conflict_result.conflict_level == ConflictLevel.NONE:
            return "pass"

        # 氛围=紧急 + 冲突=TOLERABLE → pass
        if (
            atmosphere in ["urgent", "tense"]
            and conflict_result.conflict_level == ConflictLevel.TOLERABLE
        ):
            logger.info(
                "[review_context] 紧急情况容忍轻微偏差：atmosphere=%s, conflict=%s",
                atmosphere,
                conflict_result.conflict_level.value,
            )
            return "pass"

        # 情绪=friendly + 冲突=TOLERABLE → pass
        if emotion == "friendly" and conflict_result.conflict_level == ConflictLevel.TOLERABLE:
            logger.info(
                "[review_context] 友好对话容忍偏差：emotion=%s, conflict=%s",
                emotion,
                conflict_result.conflict_level.value,
            )
            return "pass"

        # 氛围=紧张 + 冲突=NEED_INTERVENTION → block
        if (
            atmosphere in ["tense", "urgent"]
            and conflict_result.conflict_level == ConflictLevel.NEED_INTERVENTION
        ):
            logger.warning(
                "[review_context] 紧张时严格把关：atmosphere=%s, conflict=%s",
                atmosphere,
                conflict_result.conflict_level.value,
            )
            return "block"

        # 意图=defend_identity + 冲突=NEED_INTERVENTION → review
        if (
            intent == "defend_identity"
            and conflict_result.conflict_level == ConflictLevel.NEED_INTERVENTION
        ):
            logger.info(
                "[review_context] 身份相关需重新审视：intent=%s, conflict=%s",
                intent,
                conflict_result.conflict_level.value,
            )
            return "review"

        # 默认处理
        if conflict_result.conflict_level == ConflictLevel.SEVERE:
            return "block"
        elif conflict_result.conflict_level == ConflictLevel.NEED_INTERVENTION:
            return "review"
        else:
            return "pass"


class ReviewAgent(BaseAgent):
    """审视 Agent — 4 维度冲突检测

    4 个冲突检测维度：
    1. lexical — 词汇冲突：是否使用了不应使用的词（违禁词、不当用语）
    2. syntactic — 句法冲突：句式是否偏离锚定风格
    3. semantic — 语义冲突：含义是否与硬事实矛盾
    4. tonal — 语调冲突：语调是否与当前氛围/情绪不匹配

    流程：
    1. 4 维度冲突检测 → 4 个 ConflictDetectionResult
    2. 综合判定 conflict_level
    3. ReviewAgentContextExtension 语境理解扩展 → context_aware_judge
    4. 返回审视结果
    """

    def __init__(
        self,
        agent_config: Optional[AgentConfig] = None,
    ):
        """初始化审视 Agent

        Args:
            agent_config: Agent 配置
        """
        if agent_config is None:
            agent_config = AgentConfig(
                agent_id="review_agent_001",
                agent_type="review",
            )

        super().__init__(agent_config)

        self._context_extension = ReviewAgentContextExtension()

        # 违禁词列表
        self._forbidden_words = [
            "绝对",
            "肯定",
            "保证",
            "毫无疑问",
            "我保证",
            "我确定",
            "一定",
        ]

        logger.info("[review] 审视 Agent 初始化完成")

    async def process(self, message: AgentMessage) -> AgentMessage:
        """处理消息

        Args:
            message: 输入消息

        Returns:
            AgentMessage: 输出消息
        """
        try:
            # 解析输入
            content = message.content
            response_text = content.get("response", "")
            context_data = content.get("context", {})

            # Step 1: 4 维度冲突检测
            lexical_result = self._detect_lexical_conflict(response_text)
            syntactic_result = self._detect_syntactic_conflict(response_text, context_data)
            semantic_result = self._detect_semantic_conflict(response_text, context_data)
            tonal_result = self._detect_tonal_conflict(response_text, context_data)

            # Step 2: 综合判定
            overall_level = self._determine_overall_level(
                [
                    lexical_result,
                    syntactic_result,
                    semantic_result,
                    tonal_result,
                ]
            )

            # Step 3: 语境理解扩展
            atmosphere = context_data.get("atmosphere", "daily")
            emotion = context_data.get("emotion", "neutral")
            intent = context_data.get("intent")

            context_aware_judge = self._context_extension.extend(
                conflict_result=ConflictDetectionResult(
                    conflict_score=overall_level.value,
                    conflict_level=overall_level,
                ),
                atmosphere=atmosphere,
                emotion=emotion,
                intent=intent,
            )

            # 构建输出
            output = {
                "lexical_conflict": lexical_result.to_dict(),
                "syntactic_conflict": syntactic_result.to_dict(),
                "semantic_conflict": semantic_result.to_dict(),
                "tonal_conflict": tonal_result.to_dict(),
                "overall_conflict_level": overall_level.value,
                "context_aware_judge": context_aware_judge,
                "review_passed": context_aware_judge == "pass",
            }

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
                "[review] 审视完成：overall=%s, judge=%s",
                overall_level.value,
                context_aware_judge,
            )

            return response_message

        except Exception as e:
            logger.exception("[review] 处理失败：%s", e)
            raise

    def _detect_lexical_conflict(self, response: str) -> ConflictDetectionResult:
        """检测词汇冲突

        Args:
            response: 回复文本

        Returns:
            ConflictDetectionResult: 冲突检测结果
        """
        # 检测违禁词
        forbidden_count = sum(1 for word in self._forbidden_words if word in response)

        # 计算冲突分数
        if len(response) == 0:
            conflict_score = 0.0
        else:
            conflict_score = min(1.0, forbidden_count / 5)

        # 确定冲突级别
        if conflict_score == 0:
            level = ConflictLevel.NONE
        elif conflict_score < 0.3:
            level = ConflictLevel.TOLERABLE
        elif conflict_score < 0.6:
            level = ConflictLevel.NEED_INTERVENTION
        else:
            level = ConflictLevel.SEVERE

        return ConflictDetectionResult(
            conflict_score=conflict_score,
            conflict_level=level,
            conflict_type="lexical",
            details={
                "forbidden_words_found": forbidden_count,
                "forbidden_words": [w for w in self._forbidden_words if w in response],
            },
        )

    def _detect_syntactic_conflict(
        self,
        response: str,
        context_data: Dict[str, Any],
    ) -> ConflictDetectionResult:
        """检测句法冲突

        Args:
            response: 回复文本
            context_data: 上下文数据

        Returns:
            ConflictDetectionResult: 冲突检测结果
        """
        # 简化实现：检测句子长度变化
        style_dimensions = context_data.get("style_dimensions", {})
        expected_concise = style_dimensions.get("concise", 0.5)

        # 计算平均句子长度
        sentences = response.split("。")
        if len(sentences) == 0:
            avg_length = 0
        else:
            avg_length = sum(len(s) for s in sentences) / len(sentences)

        # 简洁风格期望短句
        if expected_concise > 0.7 and avg_length > 50:
            conflict_score = 0.6
            level = ConflictLevel.NEED_INTERVENTION
        elif expected_concise < 0.3 and avg_length < 20:
            conflict_score = 0.4
            level = ConflictLevel.TOLERABLE
        else:
            conflict_score = 0.1
            level = ConflictLevel.NONE

        return ConflictDetectionResult(
            conflict_score=conflict_score,
            conflict_level=level,
            conflict_type="syntactic",
            details={
                "avg_sentence_length": avg_length,
                "expected_concise": expected_concise,
            },
        )

    def _detect_semantic_conflict(
        self,
        response: str,
        context_data: Dict[str, Any],
    ) -> ConflictDetectionResult:
        """检测语义冲突

        Args:
            response: 回复文本
            context_data: 上下文数据

        Returns:
            ConflictDetectionResult: 冲突检测结果
        """
        # 检测是否与硬事实矛盾
        hard_facts = context_data.get("hard_facts", [])

        conflict_score = 0.0
        for fact in hard_facts:
            # 简化实现：检测否定词
            if "不" in response and fact in response:
                conflict_score += 0.3

        conflict_score = min(1.0, conflict_score)

        if conflict_score == 0:
            level = ConflictLevel.NONE
        elif conflict_score < 0.3:
            level = ConflictLevel.TOLERABLE
        elif conflict_score < 0.6:
            level = ConflictLevel.NEED_INTERVENTION
        else:
            level = ConflictLevel.SEVERE

        return ConflictDetectionResult(
            conflict_score=conflict_score,
            conflict_level=level,
            conflict_type="semantic",
            details={
                "hard_facts_checked": len(hard_facts),
            },
        )

    def _detect_tonal_conflict(
        self,
        response: str,
        context_data: Dict[str, Any],
    ) -> ConflictDetectionResult:
        """检测语调冲突

        Args:
            response: 回复文本
            context_data: 上下文数据

        Returns:
            ConflictDetectionResult: 冲突检测结果
        """
        # 检测语调是否与氛围/情绪匹配
        atmosphere = context_data.get("atmosphere", "daily")
        emotion = context_data.get("emotion", "neutral")

        # 简化实现：检测感叹号使用
        exclamation_count = response.count("!") + response.count("！")

        # 紧张/紧急氛围下，过多感叹号可能合适
        if atmosphere in ["tense", "urgent"]:
            conflict_score = 0.0
        elif exclamation_count > 5:
            # 日常对话中过多感叹号
            conflict_score = 0.4
        else:
            conflict_score = 0.1

        level = ConflictLevel.NONE if conflict_score < 0.2 else ConflictLevel.TOLERABLE

        return ConflictDetectionResult(
            conflict_score=conflict_score,
            conflict_level=level,
            conflict_type="tonal",
            details={
                "exclamation_count": exclamation_count,
                "atmosphere": atmosphere,
                "emotion": emotion,
            },
        )

    def _determine_overall_level(
        self,
        results: List[ConflictDetectionResult],
    ) -> ConflictLevel:
        """综合判定冲突级别

        Args:
            results: 冲突检测结果列表

        Returns:
            ConflictLevel: 综合冲突级别
        """
        # 取最高冲突级别
        level_order = {
            ConflictLevel.NONE: 0,
            ConflictLevel.TOLERABLE: 1,
            ConflictLevel.NEED_INTERVENTION: 2,
            ConflictLevel.SEVERE: 3,
        }

        max_level = ConflictLevel.NONE

        for result in results:
            if level_order[result.conflict_level] > level_order[max_level]:
                max_level = result.conflict_level

        return max_level

    async def review_prompt(self, prompt: str) -> float:
        """审查 prompt 质量并返回质量分数。

        Args:
            prompt: 待审查的 prompt 文本

        Returns:
            float: 质量分数 (0.0-1.0)
        """
        from src.models.provider import get_model_provider

        logger.info("Reviewing prompt quality (length=%d)", len(prompt))

        system = """你是一个提示词质量评估器。请评估以下 prompt 的质量，从 0.0 到 1.0 打分。

评估维度：
1. 清晰性：prompt 是否清晰明确，无歧义
2. 完整性：是否包含必要的上下文和指令
3. 可执行性：是否能指导模型生成有效输出
4. 结构化：是否有良好的组织结构

只需输出一个 0.0-1.0 之间的数字，不要包含任何其他内容。"""

        user = f"请评估以下 prompt 的质量：\n\n{prompt}"

        try:
            llm = get_model_provider()
            response = await llm.chat(system, user, temperature=0.1)

            # 解析分数
            score_text = response.strip()
            # 提取数字
            match = re.search(r"(\d+\.?\d*)", score_text)
            if match:
                score = float(match.group(1))
                # 确保在 0-1 范围内
                score = max(0.0, min(1.0, score))
                logger.debug("Prompt quality score: %.2f", score)
                return score
            else:
                logger.warning("Failed to parse quality score, defaulting to 0.5")
                return 0.5
        except Exception as e:
            logger.exception("Failed to review prompt: %s", e)
            # 出错时返回默认分数
            return 0.5

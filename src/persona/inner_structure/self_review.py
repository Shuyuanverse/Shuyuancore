# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""自审视层 v3 — 4 维度评估。

不修改回复内容，只评估回复质量并生成审视报告。
实际修改由 ArbitrateAgent 执行。

4 个维度及权重：
1. expression_authenticity (0.25) — 表达真实性
   检测 AI 助手模式：是否包含过多"我来帮你"/"当然可以"/"非常乐意"等套话

2. knowledge_honesty (0.30) — 知识诚实
   检测是否在不确定领域主动揽活

3. private_boundary (0.25) — 隐私边界
   检测是否泄露用户隐私或主动询问敏感信息

4. voice_fidelity (0.20) — 声音忠实度
   检测回复是否偏离锚定风格

评估逻辑：
- 每维度 0-1 分
- ADJUST_THRESHOLD = 0.20 — 单维度低于此值触发调整建议
- EMERGENCY_THRESHOLD = 0.70 — 综合评分低于此值触发紧急审视
- 综合评分 = Σ(维度分 * 权重)
- 单维度熔断：任一维度为 0 则综合评分直接为 0
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 维度权重
WEIGHTS = {
    "expression_authenticity": 0.25,
    "knowledge_honesty": 0.30,
    "private_boundary": 0.25,
    "voice_fidelity": 0.20,
}

# 阈值
ADJUST_THRESHOLD = 0.20  # 单维度低于此值触发调整建议
EMERGENCY_THRESHOLD = 0.70  # 综合评分低于此值触发紧急审视

# AI 模板模式
AI_TEMPLATE_PATTERNS = [
    "我很乐意",
    "当然可以",
    "让我来帮你",
    "非常高兴",
    "作为一个 AI",
    "作为一个助手",
    "我的职责是",
    "我很抱歉",
    "非常抱歉",
    "对不起",
    "我建议您",
    "您可以考虑",
    "您不妨试试",
    "希望能帮到你",
    "有什么问题随时问我",
]

# 事实断言模式
FACT_ASSERTION_PATTERNS = [
    r"我知道.{0,10}(是 | 有 | 在)",
    r"根据 (我的 | 权威).{0,10}(数据 | 信息 | 知识)",
    r"(一定 | 肯定 | 绝对 | 必然).{0,15}(是 | 会 | 能)",
    r"我保证",
    r"我确定",
    r"毫无疑问",
]

# 隐私话题模式
PRIVATE_TOPIC_PATTERNS = [
    "你的密码",
    "你的银行",
    "你的身份证",
    "你的社保",
    "你的收入",
    "你的住址",
    "你的电话号码",
    "你的邮箱",
    "你的账号",
    "你的隐私",
    "你的个人信息",
]


@dataclass
class SelfReviewResult:
    """自审视结果"""

    expression_score: float = 1.0  # 表达真实性得分
    knowledge_score: float = 1.0  # 知识诚实得分
    privacy_score: float = 1.0  # 隐私边界得分
    voice_score: float = 1.0  # 声音忠实度得分
    overall_score: float = 1.0  # 综合评分
    needs_adjustment: bool = False  # 是否需要调整
    emergency: bool = False  # 是否紧急
    adjustment_suggestions: List[str] = field(default_factory=list)  # 调整建议
    violated_dimensions: List[str] = field(default_factory=list)  # 违规维度
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "expression_score": self.expression_score,
            "knowledge_score": self.knowledge_score,
            "privacy_score": self.privacy_score,
            "voice_score": self.voice_score,
            "overall_score": self.overall_score,
            "needs_adjustment": self.needs_adjustment,
            "emergency": self.emergency,
            "adjustment_suggestions": self.adjustment_suggestions,
            "violated_dimensions": self.violated_dimensions,
            "metadata": self.metadata,
        }


class SelfReviewLayer:
    """自审视层 — 4 维度评估

    不修改回复内容，只评估回复质量并生成审视报告。
    实际修改由 ArbitrateAgent 执行。

    4 个维度及权重：
    1. expression_authenticity (0.25) — 表达真实性
    2. knowledge_honesty (0.30) — 知识诚实
    3. private_boundary (0.25) — 隐私边界
    4. voice_fidelity (0.20) — 声音忠实度
    """

    def __init__(self):
        """初始化自审视层"""
        logger.info("[self_review] 自审视层初始化完成")

    def review(
        self,
        response: str,
        style_dimensions: Optional[Dict[str, Any]] = None,
        persona_id: str = "",
    ) -> SelfReviewResult:
        """审视回复

        Args:
            response: 回复文本
            style_dimensions: 风格维度（可选，用于声音忠实度评估）
            persona_id: 人格 ID

        Returns:
            SelfReviewResult: 自审视结果

        评估逻辑：
        1. 每维度 0-1 分
        2. ADJUST_THRESHOLD = 0.20 — 单维度低于此值触发调整建议
        3. EMERGENCY_THRESHOLD = 0.70 — 综合评分低于此值触发紧急审视
        4. 综合评分 = Σ(维度分 * 权重)
        5. 单维度熔断：任一维度为 0 则综合评分直接为 0
        """
        result = SelfReviewResult()

        # Step 1: 表达真实性评估
        result.expression_score = self._evaluate_expression_authenticity(response)

        # Step 2: 知识诚实评估
        result.knowledge_score = self._evaluate_knowledge_honesty(response)

        # Step 3: 隐私边界评估
        result.privacy_score = self._evaluate_private_boundary(response)

        # Step 4: 声音忠实度评估
        result.voice_score = self._evaluate_voice_fidelity(
            response,
            style_dimensions,
        )

        # Step 5: 计算综合评分
        result.overall_score = self._calculate_overall_score(result)

        # Step 6: 检查是否需要调整
        result.needs_adjustment = self._check_needs_adjustment(result)

        # Step 7: 检查是否紧急
        result.emergency = result.overall_score < EMERGENCY_THRESHOLD

        # Step 8: 生成调整建议
        result.adjustment_suggestions = self._generate_suggestions(result)

        # Step 9: 记录违规维度
        result.violated_dimensions = self._get_violated_dimensions(result)

        # Step 10: 元数据
        result.metadata = {
            "persona_id": persona_id,
            "response_length": len(response),
            "weights": WEIGHTS,
            "adjust_threshold": ADJUST_THRESHOLD,
            "emergency_threshold": EMERGENCY_THRESHOLD,
        }

        logger.info(
            "[self_review] 审视完成：persona=%s, overall=%.2f, needs_adjustment=%s, emergency=%s",
            persona_id,
            result.overall_score,
            result.needs_adjustment,
            result.emergency,
        )

        return result

    def _evaluate_expression_authenticity(self, response: str) -> float:
        """评估表达真实性

        Args:
            response: 回复文本

        Returns:
            float: 得分 0-1

        检测 AI 助手模式：是否包含过多"我来帮你"/"当然可以"/"非常乐意"等套话
        """
        if not response:
            return 0.0

        # 统计 AI 模板出现次数
        ai_pattern_count = sum(1 for pattern in AI_TEMPLATE_PATTERNS if pattern in response)

        # 归一化到 0-1（出现 0 次得 1 分，每多 1 次扣 0.2 分）
        score = max(0.0, 1.0 - ai_pattern_count * 0.2)

        if ai_pattern_count > 0:
            logger.debug(
                "[self_review] 表达真实性：检测到 %d 个 AI 模板，得分=%.2f",
                ai_pattern_count,
                score,
            )

        return score

    def _evaluate_knowledge_honesty(self, response: str) -> float:
        """评估知识诚实

        Args:
            response: 回复文本

        Returns:
            float: 得分 0-1

        检测是否在不确定领域主动揽活
        """
        if not response:
            return 0.0

        # 统计事实断言出现次数
        assertion_count = 0
        for pattern in FACT_ASSERTION_PATTERNS:
            if re.search(pattern, response):
                assertion_count += 1

        # 归一化到 0-1（出现 0 次得 1 分，每多 1 次扣 0.25 分）
        score = max(0.0, 1.0 - assertion_count * 0.25)

        if assertion_count > 0:
            logger.debug(
                "[self_review] 知识诚实：检测到 %d 个事实断言，得分=%.2f",
                assertion_count,
                score,
            )

        return score

    def _evaluate_private_boundary(self, response: str) -> float:
        """评估隐私边界

        Args:
            response: 回复文本

        Returns:
            float: 得分 0-1

        检测是否泄露用户隐私或主动询问敏感信息
        """
        if not response:
            return 0.0

        # 统计隐私话题出现次数
        private_topic_count = sum(1 for pattern in PRIVATE_TOPIC_PATTERNS if pattern in response)

        # 归一化到 0-1（出现 0 次得 1 分，每多 1 次扣 0.3 分）
        score = max(0.0, 1.0 - private_topic_count * 0.3)

        if private_topic_count > 0:
            logger.warning(
                "[self_review] 隐私边界：检测到 %d 个隐私话题，得分=%.2f",
                private_topic_count,
                score,
            )

        return score

    def _evaluate_voice_fidelity(
        self,
        response: str,
        style_dimensions: Optional[Dict[str, Any]] = None,
    ) -> float:
        """评估声音忠实度

        Args:
            response: 回复文本
            style_dimensions: 风格维度（可选）

        Returns:
            float: 得分 0-1

        检测回复是否偏离锚定风格
        基于 StyleDimensions 的 7 维偏差计算

        简化实现：如果没有 style_dimensions，返回 1.0（默认不偏离）
        """
        if not style_dimensions:
            return 1.0

        # TODO: 实现基于风格维度的偏差计算
        # 目前简化处理：返回 1.0
        return 1.0

    def _calculate_overall_score(self, result: SelfReviewResult) -> float:
        """计算综合评分

        Args:
            result: 自审视结果

        Returns:
            float: 综合评分 0-1

        逻辑：
        - 综合评分 = Σ(维度分 * 权重)
        - 单维度熔断：任一维度为 0 则综合评分直接为 0
        """
        # 检查单维度熔断
        if (
            result.expression_score == 0.0
            or result.knowledge_score == 0.0
            or result.privacy_score == 0.0
            or result.voice_score == 0.0
        ):
            logger.warning("[self_review] 单维度熔断触发，综合评分=0.0")
            return 0.0

        # 加权平均
        overall = (
            result.expression_score * WEIGHTS["expression_authenticity"]
            + result.knowledge_score * WEIGHTS["knowledge_honesty"]
            + result.privacy_score * WEIGHTS["private_boundary"]
            + result.voice_score * WEIGHTS["voice_fidelity"]
        )

        return round(overall, 4)

    def _check_needs_adjustment(self, result: SelfReviewResult) -> bool:
        """检查是否需要调整

        Args:
            result: 自审视结果

        Returns:
            bool: 是否需要调整

        逻辑：
        - 任一维度低于 ADJUST_THRESHOLD 则触发
        """
        return (
            result.expression_score < ADJUST_THRESHOLD
            or result.knowledge_score < ADJUST_THRESHOLD
            or result.privacy_score < ADJUST_THRESHOLD
            or result.voice_score < ADJUST_THRESHOLD
        )

    def _generate_suggestions(self, result: SelfReviewResult) -> List[str]:
        """生成调整建议

        Args:
            result: 自审视结果

        Returns:
            List[str]: 调整建议列表
        """
        suggestions = []

        if result.expression_score < ADJUST_THRESHOLD:
            suggestions.append(
                "减少 AI 套话（如'我很乐意'、'当然可以'、'作为一个 AI'），使用更自然的表达"
            )

        if result.knowledge_score < ADJUST_THRESHOLD:
            suggestions.append(
                "避免绝对化断言（如'我保证'、'我确定'、'毫无疑问'），在不确定领域保持谦逊"
            )

        if result.privacy_score < ADJUST_THRESHOLD:
            suggestions.append("避免涉及用户隐私话题（如密码、银行、身份证、收入等），保护用户隐私")

        if result.voice_score < ADJUST_THRESHOLD:
            suggestions.append("保持风格一致性，避免偏离锚定风格")

        if result.emergency:
            suggestions.insert(0, "【紧急】综合评分偏低，需要立即调整")

        return suggestions

    def _get_violated_dimensions(self, result: SelfReviewResult) -> List[str]:
        """获取违规维度

        Args:
            result: 自审视结果

        Returns:
            List[str]: 违规维度列表
        """
        violated = []

        if result.expression_score < ADJUST_THRESHOLD:
            violated.append("expression_authenticity")

        if result.knowledge_score < ADJUST_THRESHOLD:
            violated.append("knowledge_honesty")

        if result.privacy_score < ADJUST_THRESHOLD:
            violated.append("private_boundary")

        if result.voice_score < ADJUST_THRESHOLD:
            violated.append("voice_fidelity")

        return violated

    def get_dimension_names(self) -> List[str]:
        """获取维度名称列表

        Returns:
            List[str]: 维度名称列表
        """
        return list(WEIGHTS.keys())

    def get_weights(self) -> Dict[str, float]:
        """获取权重字典

        Returns:
            Dict[str, float]: 权重字典
        """
        return WEIGHTS.copy()

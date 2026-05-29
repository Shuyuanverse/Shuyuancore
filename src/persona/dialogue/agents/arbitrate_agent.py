# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""仲裁 Agent — 冲突修正。

包含：
- CorrectionStrategy：修正策略
- VectorSpaceCorrector：向量空间投影修正
- ArbitrationResult：仲裁结果
- ArbitrateAgent：仲裁 Agent
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base_agent import AgentConfig, BaseAgent
from .agent_protocol import AgentMessage, MessageType
from .review_agent import ConflictDetectionResult, ConflictLevel

logger = logging.getLogger(__name__)


class CorrectionStrategy(Enum):
    """修正策略"""

    MINIMAL = "minimal"  # 最小修正：只替换冲突词
    PARTIAL = "partial"  # 部分修正：重写冲突段落
    FULL = "full"  # 完全修正：重新生成
    GRADUAL = "gradual"  # 渐进修正：多轮微调


@dataclass
class ArbitrationResult:
    """仲裁结果

    Attributes:
        corrected_response: 修正后回复
        original_response: 原始回复
        strategy_used: 使用的修正策略
        correction_count: 修正次数
        alignment_before: 修正前对齐度
        alignment_after: 修正后对齐度
        success: 是否成功
        metadata: 元数据
    """

    corrected_response: str
    original_response: str
    strategy_used: CorrectionStrategy
    correction_count: int = 0
    alignment_before: float = 0.0
    alignment_after: float = 0.0
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "corrected_response": self.corrected_response,
            "original_response": self.original_response,
            "strategy_used": self.strategy_used.value,
            "correction_count": self.correction_count,
            "alignment_before": self.alignment_before,
            "alignment_after": self.alignment_after,
            "success": self.success,
            "metadata": self.metadata,
        }


class VectorSpaceCorrector:
    """向量空间投影修正

    核心公式：h_correct = p_orig + λ·(c - proj(p_orig, c))

    其中：
    - p_orig: 原始回复向量
    - c: 约束向量（锚定风格）
    - proj(p_orig, c): p_orig 在 c 上的投影
    - λ: 修正强度（默认 0.5）
    - h_correct: 修正后向量

    最大 3 次修正，每次降低λ值（0.5 → 0.3 → 0.1）
    """

    def __init__(self, max_iterations: int = 3):
        """初始化向量空间修正器

        Args:
            max_iterations: 最大迭代次数
        """
        self.max_iterations = max_iterations
        self._lambda_values = [0.5, 0.3, 0.1]  # 修正强度递减
        logger.info("[vector_corrector] 初始化完成，max_iterations=%d", max_iterations)

    def correct(
        self,
        response_vector: np.ndarray,
        constraint_vector: np.ndarray,
    ) -> Tuple[np.ndarray, int, float]:
        """执行向量空间修正

        Args:
            response_vector: 原始回复向量
            constraint_vector: 约束向量（锚定风格）

        Returns:
            Tuple[corrected_vector, iteration_count, final_lambda]: 修正后向量、迭代次数、最终λ值
        """
        p_orig = response_vector.astype(float)
        c = constraint_vector.astype(float)

        # 归一化
        c = c / np.linalg.norm(c)

        for i, lambda_val in enumerate(self._lambda_values[: self.max_iterations]):
            # 计算投影：proj(p_orig, c) = (p_orig · c) * c
            projection = np.dot(p_orig, c) * c

            # 核心公式：h_correct = p_orig + λ·(c - proj(p_orig, c))
            correction = lambda_val * (c - projection)
            h_correct = p_orig + correction

            # 检查是否满足约束
            alignment = self._calculate_alignment(h_correct, c)

            if alignment > 0.9:
                logger.info(
                    "[vector_corrector] 修正成功：iteration=%d, lambda=%.2f, alignment=%.4f",
                    i + 1,
                    lambda_val,
                    alignment,
                )
                return h_correct, i + 1, lambda_val

            # 更新原始向量
            p_orig = h_correct

        # 达到最大迭代次数
        logger.warning(
            "[vector_corrector] 达到最大迭代次数：iterations=%d, final_alignment=%.4f",
            self.max_iterations,
            alignment,
        )

        return h_correct, self.max_iterations, self._lambda_values[-1]

    def _calculate_alignment(
        self,
        vector: np.ndarray,
        constraint: np.ndarray,
    ) -> float:
        """计算对齐度（余弦相似度）

        Args:
            vector: 向量
            constraint: 约束向量

        Returns:
            float: 对齐度 0-1
        """
        norm_v = np.linalg.norm(vector)
        norm_c = np.linalg.norm(constraint)

        if norm_v == 0 or norm_c == 0:
            return 0.0

        return np.dot(vector, constraint) / (norm_v * norm_c)


class ArbitrateAgent(BaseAgent):
    """仲裁 Agent — 冲突修正

    4 种修正策略（按严重度递进）：
    1. MINIMAL — 最小修正：识别冲突词→替换为风格一致词
    2. PARTIAL — 部分修正：定位冲突段落→重写该段落
    3. FULL — 完全修正：带约束重新生成整个回复
    4. GRADUAL — 渐进修正：VectorSpaceCorrector 多轮微调

    策略选择：
    - ConflictLevel.TOLERABLE → MINIMAL
    - ConflictLevel.NEED_INTERVENTION → PARTIAL
    - ConflictLevel.SEVERE → FULL
    - 如果 MINIMAL/PARTIAL 失败 → 升级策略

    每次修正后重新审视，最多 3 次
    """

    def __init__(
        self,
        agent_config: Optional[AgentConfig] = None,
    ):
        """初始化仲裁 Agent

        Args:
            agent_config: Agent 配置
        """
        if agent_config is None:
            agent_config = AgentConfig(
                agent_id="arbitrate_agent_001",
                agent_type="arbitrate",
            )

        super().__init__(agent_config)

        self._vector_corrector = VectorSpaceCorrector()
        self._max_corrections = 3
        logger.info("[arbitrate] 仲裁 Agent 初始化完成")

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
            review_result = content.get("review_result", {})
            anchor_vector = content.get("anchor_vector", [])

            # 确定冲突级别
            conflict_level_str = review_result.get("overall_conflict_level", "none")
            conflict_level = ConflictLevel(conflict_level_str)

            # 选择修正策略
            strategy = self._select_strategy(conflict_level)

            # Step 1: 执行修正
            arbitration_result = await self._arbitrate(
                response=response_text,
                review_result=review_result,
                strategy=strategy,
                anchor_vector=anchor_vector,
            )

            # Step 2: 如果失败，升级策略
            if not arbitration_result.success:
                strategy = self._upgrade_strategy(strategy)
                arbitration_result = await self._arbitrate(
                    response=response_text,
                    review_result=review_result,
                    strategy=strategy,
                    anchor_vector=anchor_vector,
                )

            # 构建输出
            output = arbitration_result.to_dict()

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
                "[arbitrate] 仲裁完成：strategy=%s, success=%s, corrections=%d",
                strategy.value,
                arbitration_result.success,
                arbitration_result.correction_count,
            )

            return response_message

        except Exception as e:
            logger.exception("[arbitrate] 处理失败：%s", e)
            raise

    def _select_strategy(self, conflict_level: ConflictLevel) -> CorrectionStrategy:
        """选择修正策略

        Args:
            conflict_level: 冲突级别

        Returns:
            CorrectionStrategy: 修正策略
        """
        strategy_map = {
            ConflictLevel.NONE: CorrectionStrategy.MINIMAL,
            ConflictLevel.TOLERABLE: CorrectionStrategy.MINIMAL,
            ConflictLevel.NEED_INTERVENTION: CorrectionStrategy.PARTIAL,
            ConflictLevel.SEVERE: CorrectionStrategy.FULL,
        }

        return strategy_map.get(conflict_level, CorrectionStrategy.MINIMAL)

    def _upgrade_strategy(
        self,
        current_strategy: CorrectionStrategy,
    ) -> CorrectionStrategy:
        """升级策略

        Args:
            current_strategy: 当前策略

        Returns:
            CorrectionStrategy: 升级后的策略
        """
        strategy_order = {
            CorrectionStrategy.MINIMAL: CorrectionStrategy.PARTIAL,
            CorrectionStrategy.PARTIAL: CorrectionStrategy.FULL,
            CorrectionStrategy.FULL: CorrectionStrategy.GRADUAL,
            CorrectionStrategy.GRADUAL: CorrectionStrategy.GRADUAL,
        }

        return strategy_order.get(current_strategy, CorrectionStrategy.GRADUAL)

    async def _arbitrate(
        self,
        response: str,
        review_result: Dict[str, Any],
        strategy: CorrectionStrategy,
        anchor_vector: List[float],
    ) -> ArbitrationResult:
        """执行仲裁

        Args:
            response: 原始回复
            review_result: 审视结果
            strategy: 修正策略
            anchor_vector: 锚点向量

        Returns:
            ArbitrationResult: 仲裁结果
        """
        corrected = response
        correction_count = 0
        alignment_before = 0.0
        alignment_after = 0.0

        try:
            if strategy == CorrectionStrategy.MINIMAL:
                # 最小修正：替换冲突词
                corrected, correction_count = self._minimal_correction(
                    response,
                    review_result,
                )

            elif strategy == CorrectionStrategy.PARTIAL:
                # 部分修正：重写冲突段落
                corrected, correction_count = self._partial_correction(
                    response,
                    review_result,
                )

            elif strategy == CorrectionStrategy.FULL:
                # 完全修正：重新生成
                corrected, correction_count = await self._full_correction(
                    response,
                    review_result,
                )

            elif strategy == CorrectionStrategy.GRADUAL:
                # 渐进修正：向量空间投影
                corrected, correction_count, alignment_after = self._gradual_correction(
                    response,
                    anchor_vector,
                )

            # 计算对齐度
            alignment_before = self._calculate_alignment(response, anchor_vector)
            alignment_after = self._calculate_alignment(corrected, anchor_vector)

            success = alignment_after > alignment_before or alignment_after > 0.8

            return ArbitrationResult(
                corrected_response=corrected,
                original_response=response,
                strategy_used=strategy,
                correction_count=correction_count,
                alignment_before=alignment_before,
                alignment_after=alignment_after,
                success=success,
                metadata={
                    "review_result": review_result,
                },
            )

        except Exception as e:
            logger.error("[arbitrate] 修正失败：%s", e)
            return ArbitrationResult(
                corrected_response=response,
                original_response=response,
                strategy_used=strategy,
                correction_count=0,
                alignment_before=alignment_before,
                alignment_after=alignment_after,
                success=False,
                metadata={
                    "error": str(e),
                },
            )

    def _minimal_correction(
        self,
        response: str,
        review_result: Dict[str, Any],
    ) -> Tuple[str, int]:
        """最小修正：替换冲突词

        Args:
            response: 原始回复
            review_result: 审视结果

        Returns:
            Tuple[str, int]: 修正后回复、修正次数
        """
        corrected = response
        count = 0

        # 替换违禁词
        forbidden_words = [
            "绝对",
            "肯定",
            "保证",
            "毫无疑问",
            "我保证",
            "我确定",
            "一定",
        ]

        for word in forbidden_words:
            if word in corrected:
                # 替换为更温和的表达
                replacement_map = {
                    "绝对": "通常",
                    "肯定": "可能",
                    "保证": "尽量",
                    "毫无疑问": "一般来说",
                    "我保证": "我尽量",
                    "我确定": "我认为",
                    "一定": "通常",
                }
                corrected = corrected.replace(word, replacement_map.get(word, ""))
                count += 1

        return corrected, count

    def _partial_correction(
        self,
        response: str,
        review_result: Dict[str, Any],
    ) -> Tuple[str, int]:
        """部分修正：重写冲突段落

        Args:
            response: 原始回复
            review_result: 审视结果

        Returns:
            Tuple[str, int]: 修正后回复、修正次数
        """
        # 简化实现：标记冲突段落
        corrected = response
        count = 1

        # 检测长句并拆分
        sentences = response.split("。")
        long_sentences = [s for s in sentences if len(s) > 50]

        if long_sentences:
            # 简化处理：添加标记
            corrected = "[部分修正] " + response
            count = len(long_sentences)

        return corrected, count

    async def _full_correction(
        self,
        response: str,
        review_result: Dict[str, Any],
    ) -> Tuple[str, int]:
        """完全修正：重新生成

        Args:
            response: 原始回复
            review_result: 审视结果

        Returns:
            Tuple[str, int]: 修正后回复、修正次数
        """
        # 简化实现：返回占位文本
        corrected = "[完全修正] 重新生成的回复..."
        count = 1

        return corrected, count

    def _gradual_correction(
        self,
        response: str,
        anchor_vector: List[float],
    ) -> Tuple[str, int, float]:
        """渐进修正：向量空间投影

        Args:
            response: 原始回复
            anchor_vector: 锚点向量

        Returns:
            Tuple[str, int, float]: 修正后回复、修正次数、最终对齐度
        """
        if not anchor_vector:
            return response, 0, 0.0

        # 将文本转换为向量（简化实现：使用长度作为伪向量）
        response_vector = np.array([len(response)] * len(anchor_vector))
        constraint_vector = np.array(anchor_vector)

        # 执行向量空间修正
        corrected_vector, iteration_count, final_lambda = self._vector_corrector.correct(
            response_vector,
            constraint_vector,
        )

        # 计算对齐度
        alignment = self._vector_corrector._calculate_alignment(
            corrected_vector,
            constraint_vector,
        )

        # 简化处理：不真正修改文本
        corrected = f"[渐进修正 λ={final_lambda}] {response}"

        return corrected, iteration_count, alignment

    def _calculate_alignment(
        self,
        response: str,
        anchor_vector: List[float],
    ) -> float:
        """计算对齐度（简化实现）

        Args:
            response: 回复文本
            anchor_vector: 锚点向量

        Returns:
            float: 对齐度 0-1
        """
        # 简化实现：基于长度相似度
        if not anchor_vector:
            return 0.5

        response_length = len(response)
        anchor_length = sum(anchor_vector) / len(anchor_vector) if anchor_vector else 0

        if anchor_length == 0:
            return 0.5

        ratio = min(response_length, anchor_length) / max(response_length, anchor_length)
        return ratio

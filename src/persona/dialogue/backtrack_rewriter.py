# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""回溯重写器 — 与 ArbitrateAgent 整合。

BacktrackRewriter 回溯重写器：
- 优先使用 ArbitrateAgent 执行重写
- 无 ArbitrateAgent 时降级为独立处理

rewrite(text, drift_score, constraints, trigger) → RewriteResult
1. 检查是否需要重写（drift_score > threshold 或 quality < threshold）
2. 查找回溯点（句子边界、段落边界、约束关键词）
3. 按策略重试：MINIMAL → PARTIAL → FULL
4. 每次失败后升级策略（patience=2 次连续失败）
5. 最多 3 次重试

_find_rewrite_points() → List[RewritePoint]
_generate_minimal_candidates() → List[RewriteCandidate]
_generate_partial_candidates() → List[RewriteCandidate]
_generate_full_candidates() → List[RewriteCandidate]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RewriteTrigger(Enum):
    """重写触发器"""
    
    DRIFT_DETECTED = "drift_detected"
    QUALITY_LOW = "quality_low"
    STYLE_MISMATCH = "style_mismatch"
    USER_FEEDBACK = "user_feedback"


class RewriteStrategy(Enum):
    """重写策略"""
    
    MINIMAL = "minimal"  # 最小改动
    PARTIAL = "partial"  # 部分重写
    FULL = "full"  # 完全重写
    HYBRID = "hybrid"  # 先最小后升级


@dataclass
class RewritePoint:
    """重写点
    
    Attributes:
        start: 起始位置
        end: 结束位置
        reason: 原因
        priority: 优先级
    """
    
    start: int
    end: int
    reason: str
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "priority": self.priority,
        }


@dataclass
class RewriteCandidate:
    """重写候选
    
    Attributes:
        text: 文本
        strategy: 策略
        confidence: 置信度
        metadata: 元数据
    """
    
    text: str
    strategy: RewriteStrategy
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text": self.text,
            "strategy": self.strategy.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class RewriteResult:
    """重写结果
    
    Attributes:
        rewritten_text: 重写后的文本
        original_text: 原始文本
        strategy_used: 使用的策略
        rewrite_count: 重写次数
        success: 是否成功
        metadata: 元数据
    """
    
    rewritten_text: str
    original_text: str
    strategy_used: RewriteStrategy
    rewrite_count: int = 0
    success: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "rewritten_text": self.rewritten_text,
            "original_text": self.original_text,
            "strategy_used": self.strategy_used.value,
            "rewrite_count": self.rewrite_count,
            "success": self.success,
            "metadata": self.metadata,
        }


class BacktrackRewriter:
    """回溯重写器 — 与 ArbitrateAgent 整合
    
    优先使用 ArbitrateAgent 执行重写
    无 ArbitrateAgent 时降级为独立处理
    
    rewrite(text, drift_score, constraints, trigger) → RewriteResult
    1. 检查是否需要重写（drift_score > threshold 或 quality < threshold）
    2. 查找回溯点（句子边界、段落边界、约束关键词）
    3. 按策略重试：MINIMAL → PARTIAL → FULL
    4. 每次失败后升级策略（patience=2 次连续失败）
    5. 最多 3 次重试
    """
    
    def __init__(self, arbitrate_agent: Optional[Any] = None):
        """初始化回溯重写器
        
        Args:
            arbitrate_agent: 仲裁 Agent（可选）
        """
        self._arbitrate_agent = arbitrate_agent
        
        # 配置
        self._drift_threshold = 0.3
        self._quality_threshold = 0.6
        self._max_retries = 3
        self._patience = 2  # 连续失败次数阈值
        
        logger.info(
            "[backtrack_rewriter] 初始化完成，drift_threshold=%.2f, max_retries=%d",
            self._drift_threshold,
            self._max_retries,
        )
    
    async def rewrite(
        self,
        text: str,
        drift_score: float,
        constraints: Any,
        trigger: RewriteTrigger,
    ) -> RewriteResult:
        """重写
        
        Args:
            text: 原始文本
            drift_score: 漂移分数
            constraints: 约束向量
            trigger: 触发器
        
        Returns:
            RewriteResult: 重写结果
        """
        # Step 1: 检查是否需要重写
        if not self._needs_rewrite(text, drift_score):
            logger.info("[backtrack_rewriter] 无需重写：drift=%.2f", drift_score)
            return RewriteResult(
                rewritten_text=text,
                original_text=text,
                strategy_used=RewriteStrategy.MINIMAL,
                success=True,
            )
        
        # Step 2: 查找回溯点
        rewrite_points = self._find_rewrite_points(text, constraints)
        
        if not rewrite_points:
            logger.warning("[backtrack_rewriter] 未找到回溯点")
            return RewriteResult(
                rewritten_text=text,
                original_text=text,
                strategy_used=RewriteStrategy.FULL,
                success=False,
                metadata={"reason": "no_rewrite_points"},
            )
        
        # Step 3: 按策略重试
        result = await self._retry_with_strategies(
            text=text,
            rewrite_points=rewrite_points,
            constraints=constraints,
            trigger=trigger,
        )
        
        logger.info(
            "[backtrack_rewriter] 重写完成：success=%s, strategy=%s, count=%d",
            result.success,
            result.strategy_used.value,
            result.rewrite_count,
        )
        
        return result
    
    def _needs_rewrite(self, text: str, drift_score: float) -> bool:
        """检查是否需要重写
        
        Args:
            text: 文本
            drift_score: 漂移分数
        
        Returns:
            bool: 是否需要重写
        """
        # 漂移超过阈值
        if drift_score > self._drift_threshold:
            return True
        
        # 简化实现：不检查质量
        return False
    
    def _find_rewrite_points(
        self,
        text: str,
        constraints: Any,
    ) -> List[RewritePoint]:
        """查找回溯点
        
        Args:
            text: 文本
            constraints: 约束向量
        
        Returns:
            List[RewritePoint]: 重写点列表
        """
        rewrite_points = []
        
        # 句子边界
        sentences = text.split("。")
        current_pos = 0
        
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            
            start = current_pos
            end = current_pos + len(sentence) + 1  # +1 for "。"
            
            # 检查是否违反约束
            if self._violates_constraint(sentence, constraints):
                rewrite_points.append(RewritePoint(
                    start=start,
                    end=end,
                    reason=f"sentence_{i}_violates_constraint",
                    priority=2,
                ))
            
            current_pos = end
        
        # 按优先级排序
        rewrite_points.sort(key=lambda p: p.priority, reverse=True)
        
        logger.debug(
            "[backtrack_rewriter] 找到 %d 个重写点",
            len(rewrite_points),
        )
        
        return rewrite_points
    
    def _violates_constraint(self, text: str, constraints: Any) -> bool:
        """检查是否违反约束
        
        Args:
            text: 文本
            constraints: 约束向量
        
        Returns:
            bool: 是否违反约束
        """
        # 简化实现：不检查
        return False
    
    async def _retry_with_strategies(
        self,
        text: str,
        rewrite_points: List[RewritePoint],
        constraints: Any,
        trigger: RewriteTrigger,
    ) -> RewriteResult:
        """按策略重试
        
        Args:
            text: 文本
            rewrite_points: 重写点
            constraints: 约束向量
            trigger: 触发器
        
        Returns:
            RewriteResult: 重写结果
        """
        current_text = text
        strategy_order = [
            RewriteStrategy.MINIMAL,
            RewriteStrategy.PARTIAL,
            RewriteStrategy.FULL,
        ]
        
        consecutive_failures = 0
        total_rewrites = 0
        
        for strategy in strategy_order:
            if consecutive_failures >= self._patience:
                logger.info(
                    "[backtrack_rewriter] 连续失败 %d 次，升级策略",
                    consecutive_failures,
                )
                consecutive_failures = 0
            
            # 生成候选
            candidates = self._generate_candidates(
                current_text,
                rewrite_points,
                constraints,
                strategy,
            )
            
            if not candidates:
                consecutive_failures += 1
                continue
            
            # 选择最佳候选
            best_candidate = max(candidates, key=lambda c: c.confidence)
            
            if best_candidate.confidence < 0.5:
                consecutive_failures += 1
                continue
            
            # 应用重写
            current_text = best_candidate.text
            total_rewrites += 1
            consecutive_failures = 0
            
            # 检查是否成功
            if self._is_successful(current_text, constraints):
                return RewriteResult(
                    rewritten_text=current_text,
                    original_text=text,
                    strategy_used=strategy,
                    rewrite_count=total_rewrites,
                    success=True,
                )
        
        # 全部失败
        return RewriteResult(
            rewritten_text=current_text,
            original_text=text,
            strategy_used=RewriteStrategy.FULL,
            rewrite_count=total_rewrites,
            success=False,
            metadata={"reason": "max_retries_exceeded"},
        )
    
    def _generate_candidates(
        self,
        text: str,
        rewrite_points: List[RewritePoint],
        constraints: Any,
        strategy: RewriteStrategy,
    ) -> List[RewriteCandidate]:
        """生成候选
        
        Args:
            text: 文本
            rewrite_points: 重写点
            constraints: 约束向量
            strategy: 策略
        
        Returns:
            List[RewriteCandidate]: 候选列表
        """
        if strategy == RewriteStrategy.MINIMAL:
            return self._generate_minimal_candidates(text, rewrite_points, constraints)
        elif strategy == RewriteStrategy.PARTIAL:
            return self._generate_partial_candidates(text, rewrite_points, constraints)
        elif strategy == RewriteStrategy.FULL:
            return self._generate_full_candidates(text, constraints)
        else:
            return []
    
    def _generate_minimal_candidates(
        self,
        text: str,
        rewrite_points: List[RewritePoint],
        constraints: Any,
    ) -> List[RewriteCandidate]:
        """生成最小改动候选"""
        candidates = []
        
        # 简化实现：只替换关键词
        for point in rewrite_points:
            segment = text[point.start:point.end]
            # 简化：不真正修改
            candidate = RewriteCandidate(
                text=segment,
                strategy=RewriteStrategy.MINIMAL,
                confidence=0.6,
            )
            candidates.append(candidate)
        
        return candidates
    
    def _generate_partial_candidates(
        self,
        text: str,
        rewrite_points: List[RewritePoint],
        constraints: Any,
    ) -> List[RewriteCandidate]:
        """生成部分重写候选"""
        candidates = []
        
        # 简化实现
        candidate = RewriteCandidate(
            text=text,
            strategy=RewriteStrategy.PARTIAL,
            confidence=0.7,
        )
        candidates.append(candidate)
        
        return candidates
    
    def _generate_full_candidates(
        self,
        text: str,
        constraints: Any,
    ) -> List[RewriteCandidate]:
        """生成完全重写候选"""
        candidates = []
        
        # 简化实现
        candidate = RewriteCandidate(
            text="【完全重写】重新生成的回复...",
            strategy=RewriteStrategy.FULL,
            confidence=0.8,
        )
        candidates.append(candidate)
        
        return candidates
    
    def _is_successful(self, text: str, constraints: Any) -> bool:
        """检查是否成功
        
        Args:
            text: 文本
            constraints: 约束向量
        
        Returns:
            bool: 是否成功
        """
        # 简化实现：总是成功
        return True

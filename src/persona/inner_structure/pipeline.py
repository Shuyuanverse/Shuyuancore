# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""内心结构管线：审视→调整建议。

Feature Flag 控制，错误兜底

orchestrate(response, style_dimensions, persona_id) → InnerStructureResult
1. SelfReviewLayer.review() → SelfReviewResult
2. 如果 needs_adjustment → 生成调整建议（不直接修改回复）
3. 如果 emergency → 标记为需要 ArbitrateAgent 处理
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .self_review import SelfReviewLayer, SelfReviewResult

logger = logging.getLogger(__name__)


@dataclass
class InnerStructureConfig:
    """内心结构配置"""
    
    enable_self_review: bool = True  # 启用自审视
    enable_adjustment_suggestions: bool = True  # 启用调整建议
    enable_emergency_alert: bool = True  # 启用紧急告警
    enable_error_fallback: bool = True  # 启用错误兜底
    
    # 阈值配置
    adjust_threshold: float = 0.20  # 调整阈值
    emergency_threshold: float = 0.70  # 紧急阈值
    
    # 调整建议配置
    max_suggestions: int = 5  # 最大建议数
    include_detailed_analysis: bool = False  # 包含详细分析


@dataclass
class AdjustmentSuggestion:
    """调整建议"""
    
    dimension: str  # 维度名称
    suggestion: str  # 建议内容
    priority: str  # 优先级：high/medium/low
    severity: float  # 严重程度 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dimension": self.dimension,
            "suggestion": self.suggestion,
            "priority": self.priority,
            "severity": self.severity,
        }


@dataclass
class InnerStructureResult:
    """内心结构结果"""
    
    self_review_result: Optional[SelfReviewResult] = None  # 自审视结果
    adjustment_suggestions: List[AdjustmentSuggestion] = field(default_factory=list)  # 调整建议
    needs_arbitrate: bool = False  # 是否需要仲裁
    errors: List[str] = field(default_factory=list)  # 错误列表
    warnings: List[str] = field(default_factory=list)  # 警告列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "self_review_result": self.self_review_result.to_dict() if self.self_review_result else None,
            "adjustment_suggestions": [s.to_dict() for s in self.adjustment_suggestions],
            "needs_arbitrate": self.needs_arbitrate,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class InnerStructurePipeline:
    """内心结构管线：审视→调整建议
    
    Feature Flag 控制，错误兜底
    
    orchestrate(response, style_dimensions, persona_id) → InnerStructureResult
    1. SelfReviewLayer.review() → SelfReviewResult
    2. 如果 needs_adjustment → 生成调整建议（不直接修改回复）
    3. 如果 emergency → 标记为需要 ArbitrateAgent 处理
    """
    
    def __init__(self, config: Optional[InnerStructureConfig] = None):
        """初始化内心结构管线
        
        Args:
            config: 配置参数
        """
        self.config = config or InnerStructureConfig()
        
        # 初始化组件
        self._self_review_layer = SelfReviewLayer()
        
        logger.info("[pipeline] 内心结构管线初始化完成，配置：%s", self.config)
    
    def orchestrate(
        self,
        response: str,
        style_dimensions: Optional[Dict[str, Any]] = None,
        persona_id: str = "",
    ) -> InnerStructureResult:
        """编排流程
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度（可选）
            persona_id: 人格 ID
        
        Returns:
            InnerStructureResult: 内心结构结果
        
        流程：
        1. SelfReviewLayer.review() → SelfReviewResult
        2. 如果 needs_adjustment → 生成调整建议（不直接修改回复）
        3. 如果 emergency → 标记为需要 ArbitrateAgent 处理
        """
        result = InnerStructureResult()
        
        try:
            # Step 1: 自审视
            if self.config.enable_self_review:
                try:
                    self_review_result = self._self_review_layer.review(
                        response=response,
                        style_dimensions=style_dimensions,
                        persona_id=persona_id,
                    )
                    result.self_review_result = self_review_result
                    result.metadata["self_review_enabled"] = True
                except Exception as e:
                    error_msg = f"自审视失败：{str(e)}"
                    logger.exception("[pipeline] %s", error_msg)
                    
                    if self.config.enable_error_fallback:
                        result.errors.append(error_msg)
                        result.warnings.append("使用默认审视结果")
                        result.self_review_result = SelfReviewResult()
                    else:
                        result.errors.append(error_msg)
                        return result
            else:
                result.warnings.append("自审视已禁用")
            
            # Step 2: 生成调整建议
            if (
                self.config.enable_adjustment_suggestions
                and result.self_review_result
                and result.self_review_result.needs_adjustment
            ):
                try:
                    suggestions = self._generate_adjustment_suggestions(
                        result.self_review_result,
                    )
                    result.adjustment_suggestions = suggestions
                    result.metadata["adjustment_suggestions_enabled"] = True
                except Exception as e:
                    error_msg = f"生成调整建议失败：{str(e)}"
                    logger.exception("[pipeline] %s", error_msg)
                    
                    if self.config.enable_error_fallback:
                        result.errors.append(error_msg)
                        result.warnings.append("无法生成调整建议")
                    else:
                        result.errors.append(error_msg)
                        return result
            
            # Step 3: 检查是否需要仲裁
            if (
                self.config.enable_emergency_alert
                and result.self_review_result
                and result.self_review_result.emergency
            ):
                result.needs_arbitrate = True
                result.warnings.append(
                    f"紧急审视触发：综合评分 {result.self_review_result.overall_score:.2f} < {self.config.emergency_threshold}"
                )
            
            result.metadata["pipeline_success"] = True
            result.metadata["step_count"] = sum([
                self.config.enable_self_review,
                self.config.enable_adjustment_suggestions and result.self_review_result.needs_adjustment if result.self_review_result else False,
            ])
            
            logger.info(
                "[pipeline] 编排完成：persona=%s, overall=%.2f, needs_arbitrate=%s, suggestions=%d",
                persona_id,
                result.self_review_result.overall_score if result.self_review_result else 0.0,
                result.needs_arbitrate,
                len(result.adjustment_suggestions),
            )
            
        except Exception as e:
            error_msg = f"管线编排失败：{str(e)}"
            logger.exception("[pipeline] %s", error_msg)
            result.errors.append(error_msg)
            result.metadata["pipeline_success"] = False
        
        return result
    
    def _generate_adjustment_suggestions(
        self,
        self_review_result: SelfReviewResult,
    ) -> List[AdjustmentSuggestion]:
        """生成调整建议
        
        Args:
            self_review_result: 自审视结果
        
        Returns:
            List[AdjustmentSuggestion]: 调整建议列表
        """
        suggestions = []
        
        # 遍历违规维度
        for dimension in self_review_result.violated_dimensions:
            # 获取维度得分
            score = getattr(self_review_result, f"{dimension}_score", 1.0)
            
            # 计算严重程度
            severity = 1.0 - score
            
            # 确定优先级
            if severity > 0.8:
                priority = "high"
            elif severity > 0.5:
                priority = "medium"
            else:
                priority = "low"
            
            # 获取建议内容
            suggestion_text = self._get_suggestion_for_dimension(dimension, severity)
            
            suggestion = AdjustmentSuggestion(
                dimension=dimension,
                suggestion=suggestion_text,
                priority=priority,
                severity=severity,
            )
            suggestions.append(suggestion)
            
            # 限制最大建议数
            if len(suggestions) >= self.config.max_suggestions:
                break
        
        # 按严重程度排序
        suggestions.sort(key=lambda s: s.severity, reverse=True)
        
        return suggestions
    
    def _get_suggestion_for_dimension(
        self,
        dimension: str,
        severity: float,
    ) -> str:
        """获取维度对应的建议
        
        Args:
            dimension: 维度名称
            severity: 严重程度
        
        Returns:
            str: 建议内容
        """
        suggestion_map = {
            "expression_authenticity": (
                "减少 AI 套话（如"我很乐意"、"当然可以"、"作为一个 AI"），"
                "使用更自然、真实的表达方式"
            ),
            "knowledge_honesty": (
                "避免绝对化断言（如"我保证"、"我确定"、"毫无疑问"），"
                "在不确定领域保持谦逊，承认知识边界"
            ),
            "private_boundary": (
                "避免涉及用户隐私话题（如密码、银行、身份证、收入等），"
                "保护用户隐私，不主动询问敏感信息"
            ),
            "voice_fidelity": (
                "保持风格一致性，避免偏离锚定风格，"
                "回顾人格画像中的风格维度定义"
            ),
        }
        
        base_suggestion = suggestion_map.get(
            dimension,
            f"检查 {dimension} 维度的表现，确保符合规范",
        )
        
        # 根据严重程度添加语气
        if severity > 0.8:
            return f"【严重】{base_suggestion}"
        elif severity > 0.5:
            return f"【中等】{base_suggestion}"
        else:
            return f"【轻微】{base_suggestion}"
    
    def quick_review(
        self,
        response: str,
        persona_id: str = "",
    ) -> SelfReviewResult:
        """快速审视（无风格维度）
        
        Args:
            response: 回复文本
            persona_id: 人格 ID
        
        Returns:
            SelfReviewResult: 自审视结果
        """
        return self._self_review_layer.review(
            response=response,
            style_dimensions=None,
            persona_id=persona_id,
        )
    
    def get_self_review_layer(self) -> SelfReviewLayer:
        """获取自审视层
        
        Returns:
            SelfReviewLayer: 自审视层实例
        """
        return self._self_review_layer

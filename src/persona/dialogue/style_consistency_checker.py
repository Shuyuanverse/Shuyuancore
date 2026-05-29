# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格一致性检测器。

检测回复是否与锚定风格一致
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StyleConsistencyResult:
    """风格一致性检测结果
    
    Attributes:
        is_consistent: 是否一致
        consistency_score: 一致性分数 0-1
        deviated_dimensions: 偏离维度列表
        suggestions: 改进建议
    """
    
    is_consistent: bool = True
    consistency_score: float = 1.0
    deviated_dimensions: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "is_consistent": self.is_consistent,
            "consistency_score": self.consistency_score,
            "deviated_dimensions": self.deviated_dimensions,
            "suggestions": self.suggestions,
        }


class StyleConsistencyChecker:
    """风格一致性检测器
    
    检测回复是否与锚定风格一致
    
    检测维度：
    1. 词汇选择：是否使用了风格不符的词汇
    2. 句式结构：句式是否与锚定风格一致
    3. 语调情感：语调是否与风格画像匹配
    4. 表达习惯：是否符合锚定的表达习惯
    """
    
    def __init__(self):
        """初始化风格一致性检测器"""
        logger.info("[style_checker] 风格一致性检测器初始化完成")
    
    def check(
        self,
        response: str,
        style_anchor: List[float],
        style_dimensions: Dict[str, Any],
    ) -> StyleConsistencyResult:
        """检查风格一致性
        
        Args:
            response: 回复文本
            style_anchor: 风格锚点向量
            style_dimensions: 风格维度
        
        Returns:
            StyleConsistencyResult: 检测结果
        """
        result = StyleConsistencyResult()
        
        # Step 1: 词汇选择检测
        lexical_score = self._check_lexical_choice(response, style_dimensions)
        
        # Step 2: 句式结构检测
        syntactic_score = self._check_syntactic_structure(response, style_dimensions)
        
        # Step 3: 语调情感检测
        tonal_score = self._check_tonal_emotion(response, style_dimensions)
        
        # Step 4: 表达习惯检测
        habit_score = self._check_expression_habits(response, style_dimensions)
        
        # Step 5: 计算综合分数
        overall_score = (
            lexical_score * 0.25
            + syntactic_score * 0.25
            + tonal_score * 0.25
            + habit_score * 0.25
        )
        
        result.consistency_score = overall_score
        result.is_consistent = overall_score > 0.7
        
        # Step 6: 识别偏离维度
        if lexical_score < 0.7:
            result.deviated_dimensions.append("lexical_choice")
            result.suggestions.append("调整词汇选择，使其更符合风格锚点")
        
        if syntactic_score < 0.7:
            result.deviated_dimensions.append("syntactic_structure")
            result.suggestions.append("调整句式结构，使其更符合锚定风格")
        
        if tonal_score < 0.7:
            result.deviated_dimensions.append("tonal_emotion")
            result.suggestions.append("调整语调和情感表达")
        
        if habit_score < 0.7:
            result.deviated_dimensions.append("expression_habits")
            result.suggestions.append("调整表达习惯，使用更符合人格的措辞")
        
        logger.info(
            "[style_checker] 检测完成：consistency=%.2f, is_consistent=%s",
            overall_score,
            result.is_consistent,
        )
        
        return result
    
    def _check_lexical_choice(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
    ) -> float:
        """检测词汇选择
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度
        
        Returns:
            float: 分数 0-1
        """
        # 简化实现：基于正式度检测
        formal_score = style_dimensions.get("formal", 0.5)
        colloquial_score = style_dimensions.get("colloquial", 0.5)
        
        # 检测正式词汇
        formal_words = ["您", "请", "贵", "敬语", "正式"]
        colloquial_words = ["咱", "俺", "啥", "咋", "口语"]
        
        formal_count = sum(1 for word in formal_words if word in response)
        colloquial_count = sum(1 for word in colloquial_words if word in response)
        
        # 计算匹配度
        if formal_score > colloquial_score:
            # 期望正式
            if formal_count >= colloquial_count:
                return 1.0
            else:
                return 0.5
        else:
            # 期望口语
            if colloquial_count >= formal_count:
                return 1.0
            else:
                return 0.5
    
    def _check_syntactic_structure(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
    ) -> float:
        """检测句式结构
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度
        
        Returns:
            float: 分数 0-1
        """
        # 检测简洁度
        concise_score = style_dimensions.get("concise", 0.5)
        
        # 计算平均句子长度
        sentences = response.split("。")
        if len(sentences) == 0:
            return 1.0
        
        avg_length = sum(len(s) for s in sentences) / len(sentences)
        
        # 简洁风格期望短句
        if concise_score > 0.7:
            if avg_length < 30:
                return 1.0
            elif avg_length < 50:
                return 0.7
            else:
                return 0.4
        else:
            # 非简洁风格允许长句
            if avg_length > 30:
                return 1.0
            else:
                return 0.8
    
    def _check_tonal_emotion(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
    ) -> float:
        """检测语调情感
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度
        
        Returns:
            float: 分数 0-1
        """
        # 检测情感表达度
        emotional_score = style_dimensions.get("emotional", 0.5)
        
        # 检测感叹号
        exclamation_count = response.count("!") + response.count("！")
        
        # 高情感表达期望更多感叹号
        if emotional_score > 0.7:
            if exclamation_count > 2:
                return 1.0
            else:
                return 0.6
        else:
            # 低情感表达期望较少感叹号
            if exclamation_count < 2:
                return 1.0
            else:
                return 0.7
    
    def _check_expression_habits(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
    ) -> float:
        """检测表达习惯
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度
        
        Returns:
            float: 分数 0-1
        """
        # 简化实现：检测互动性
        interactive_score = style_dimensions.get("interactive", 0.5)
        
        # 检测问句
        question_count = response.count("?") + response.count("？")
        
        # 高互动性期望更多问句
        if interactive_score > 0.7:
            if question_count > 0:
                return 1.0
            else:
                return 0.6
        else:
            # 低互动性期望较少问句
            if question_count < 2:
                return 1.0
            else:
                return 0.8

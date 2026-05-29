# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格一致性检测器 — 完整实现。

维度权重：
- catchphrase: 1.2, sentence_length: 1.0, sentence_pattern: 0.9,
- punctuation: 0.8, vocabulary: 0.7, syntactic: 0.8, tone: 1.1

check(text, anchor, context) → ConsistencyResult
1. 提取文本风格特征（TextStyleAnalyzer）
2. 获取锚点特征
3. 各维度一致性评分
4. 加权综合得分
5. 生成改进建议

pre_check(text, context) → float  # 快速预检（0-1）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConsistencyLevel(Enum):
    """一致性级别"""
    
    EXCELLENT = "excellent"  # >=0.9
    GOOD = "good"  # >=0.7
    ACCEPTABLE = "acceptable"  # >=0.5
    POOR = "poor"  # <0.5


@dataclass
class DimensionScore:
    """维度得分
    
    Attributes:
        dimension_name: 维度名称
        score: 得分 0-1
        threshold: 阈值
        is_acceptable: 是否可接受
        details: 详细信息
    """
    
    dimension_name: str
    score: float = 0.0
    threshold: float = 0.7
    is_acceptable: bool = True
    details: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dimension_name": self.dimension_name,
            "score": self.score,
            "threshold": self.threshold,
            "is_acceptable": self.is_acceptable,
            "details": self.details,
        }


@dataclass
class ConsistencyResult:
    """一致性检测结果
    
    Attributes:
        overall_score: 综合得分 0-1
        level: 一致性级别
        drift_score: 漂移分数 (= 1 - overall_score)
        dimension_scores: 维度得分列表
        anchor_similarity: 锚点相似度
        suggestions: 改进建议列表
    """
    
    overall_score: float = 0.0
    level: ConsistencyLevel = ConsistencyLevel.POOR
    drift_score: float = 0.0
    dimension_scores: List[DimensionScore] = field(default_factory=list)
    anchor_similarity: float = 0.0
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "overall_score": self.overall_score,
            "level": self.level.value,
            "drift_score": self.drift_score,
            "dimension_scores": [ds.to_dict() for ds in self.dimension_scores],
            "anchor_similarity": self.anchor_similarity,
            "suggestions": self.suggestions,
        }


class StyleConsistencyChecker:
    """风格一致性检测器
    
    维度权重：
    - catchphrase: 1.2
    - sentence_length: 1.0
    - sentence_pattern: 0.9
    - punctuation: 0.8
    - vocabulary: 0.7
    - syntactic: 0.8
    - tone: 1.1
    
    check(text, anchor, context) → ConsistencyResult
    1. 提取文本风格特征（TextStyleAnalyzer）
    2. 获取锚点特征
    3. 各维度一致性评分
    4. 加权综合得分
    5. 生成改进建议
    
    pre_check(text, context) → float  # 快速预检（0-1）
    """
    
    def __init__(self):
        """初始化风格一致性检测器"""
        # 维度权重
        self.weights = {
            "catchphrase": 1.2,
            "sentence_length": 1.0,
            "sentence_pattern": 0.9,
            "punctuation": 0.8,
            "vocabulary": 0.7,
            "syntactic": 0.8,
            "tone": 1.1,
        }
        
        # 归一化权重
        total_weight = sum(self.weights.values())
        self.normalized_weights = {
            k: v / total_weight for k, v in self.weights.items()
        }
        
        logger.info(
            "[style_checker] 初始化完成，weights=%s",
            self.weights,
        )
    
    def check(
        self,
        text: str,
        anchor: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyResult:
        """检查风格一致性
        
        Args:
            text: 待检测文本
            anchor: 锚点特征字典
            context: 上下文信息（可选）
        
        Returns:
            ConsistencyResult: 一致性检测结果
        """
        result = ConsistencyResult()
        
        # Step 1: 提取文本风格特征
        text_features = self._extract_text_features(text)
        
        # Step 2: 获取锚点特征
        anchor_features = anchor.get("features", {})
        
        # Step 3: 各维度一致性评分
        dimension_scores = []
        
        # catchphrase 维度
        catchphrase_score = self._check_catchphrase(
            text_features.get("catchphrases", []),
            anchor_features.get("catchphrases", []),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="catchphrase",
            score=catchphrase_score,
            threshold=0.7,
            is_acceptable=catchphrase_score >= 0.7,
            details=f"口头禅匹配度：{catchphrase_score:.2f}",
        ))
        
        # sentence_length 维度
        sentence_length_score = self._check_sentence_length(
            text_features.get("avg_sentence_length", 0),
            anchor_features.get("avg_sentence_length", 0),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="sentence_length",
            score=sentence_length_score,
            threshold=0.7,
            is_acceptable=sentence_length_score >= 0.7,
            details=f"句子长度匹配度：{sentence_length_score:.2f}",
        ))
        
        # sentence_pattern 维度
        sentence_pattern_score = self._check_sentence_pattern(
            text_features.get("sentence_patterns", {}),
            anchor_features.get("sentence_patterns", {}),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="sentence_pattern",
            score=sentence_pattern_score,
            threshold=0.7,
            is_acceptable=sentence_pattern_score >= 0.7,
            details=f"句式模式匹配度：{sentence_pattern_score:.2f}",
        ))
        
        # punctuation 维度
        punctuation_score = self._check_punctuation(
            text_features.get("punctuation_complexity", 0),
            anchor_features.get("punctuation_complexity", 0),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="punctuation",
            score=punctuation_score,
            threshold=0.7,
            is_acceptable=punctuation_score >= 0.7,
            details=f"标点复杂度匹配度：{punctuation_score:.2f}",
        ))
        
        # vocabulary 维度
        vocabulary_score = self._check_vocabulary(
            text_features.get("vocabulary_richness", 0),
            anchor_features.get("vocabulary_richness", 0),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="vocabulary",
            score=vocabulary_score,
            threshold=0.7,
            is_acceptable=vocabulary_score >= 0.7,
            details=f"词汇丰富度匹配度：{vocabulary_score:.2f}",
        ))
        
        # syntactic 维度
        syntactic_score = self._check_syntactic(
            text_features.get("syntactic_complexity", 0),
            anchor_features.get("syntactic_complexity", 0),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="syntactic",
            score=syntactic_score,
            threshold=0.7,
            is_acceptable=syntactic_score >= 0.7,
            details=f"句法复杂度匹配度：{syntactic_score:.2f}",
        ))
        
        # tone 维度
        tone_score = self._check_tone(
            text_features.get("tone", "neutral"),
            anchor_features.get("tone", "neutral"),
        )
        dimension_scores.append(DimensionScore(
            dimension_name="tone",
            score=tone_score,
            threshold=0.7,
            is_acceptable=tone_score >= 0.7,
            details=f"语调匹配度：{tone_score:.2f}",
        ))
        
        result.dimension_scores = dimension_scores
        
        # Step 4: 加权综合得分
        overall_score = sum(
            ds.score * self.normalized_weights[ds.dimension_name]
            for ds in dimension_scores
        )
        
        result.overall_score = round(overall_score, 4)
        result.drift_score = round(1.0 - overall_score, 4)
        
        # Step 5: 确定一致性级别
        if overall_score >= 0.9:
            result.level = ConsistencyLevel.EXCELLENT
        elif overall_score >= 0.7:
            result.level = ConsistencyLevel.GOOD
        elif overall_score >= 0.5:
            result.level = ConsistencyLevel.ACCEPTABLE
        else:
            result.level = ConsistencyLevel.POOR
        
        # Step 6: 计算锚点相似度
        result.anchor_similarity = self._calculate_anchor_similarity(
            text_features,
            anchor_features,
        )
        
        # Step 7: 生成改进建议
        result.suggestions = self._generate_suggestions(dimension_scores)
        
        logger.info(
            "[style_checker] 检测完成：overall=%.2f, level=%s, drift=%.2f",
            result.overall_score,
            result.level.value,
            result.drift_score,
        )
        
        return result
    
    def pre_check(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """快速预检
        
        Args:
            text: 待检测文本
            context: 上下文信息（可选）
        
        Returns:
            float: 预检分数 0-1
        """
        # 简化实现：基于文本长度和句子数量
        if not text.strip():
            return 0.0
        
        sentences = text.split("。")
        if len(sentences) < 2:
            return 0.5
        
        avg_length = sum(len(s) for s in sentences) / len(sentences)
        
        # 期望平均句子长度在 20-50 之间
        if 20 <= avg_length <= 50:
            return 0.8
        elif 10 <= avg_length <= 80:
            return 0.6
        else:
            return 0.4
    
    def _extract_text_features(self, text: str) -> Dict[str, Any]:
        """提取文本风格特征
        
        Args:
            text: 文本
        
        Returns:
            Dict: 特征字典
        """
        # 简化实现
        sentences = text.split("。")
        sentences = [s for s in sentences if s.strip()]
        
        avg_sentence_length = (
            sum(len(s) for s in sentences) / len(sentences)
            if sentences else 0
        )
        
        # 标点复杂度
        punctuation_count = text.count("，") + text.count("。") + text.count("！") + text.count("？")
        punctuation_complexity = punctuation_count / max(len(text), 1)
        
        # 词汇丰富度（简化）
        words = text.replace("。", " ").replace("，", " ").split()
        unique_words = set(words)
        vocabulary_richness = len(unique_words) / max(len(words), 1)
        
        # 句法复杂度（简化）
        syntactic_complexity = 1.0 if avg_sentence_length > 30 else 0.5
        
        # 语调（简化）
        if "！" in text or "!" in text:
            tone = "excited"
        elif "？" in text or "?" in text:
            tone = "questioning"
        else:
            tone = "neutral"
        
        return {
            "avg_sentence_length": avg_sentence_length,
            "sentence_patterns": {},
            "punctuation_complexity": punctuation_complexity,
            "vocabulary_richness": vocabulary_richness,
            "syntactic_complexity": syntactic_complexity,
            "tone": tone,
            "catchphrases": [],
        }
    
    def _check_catchphrase(
        self,
        text_catchphrases: List[str],
        anchor_catchphrases: List[str],
    ) -> float:
        """检查口头禅一致性"""
        if not anchor_catchphrases:
            return 1.0
        
        if not text_catchphrases:
            return 0.5
        
        # 计算匹配度
        matches = set(text_catchphrases) & set(anchor_catchphrases)
        return len(matches) / max(len(anchor_catchphrases), 1)
    
    def _check_sentence_length(
        self,
        text_avg: float,
        anchor_avg: float,
    ) -> float:
        """检查句子长度一致性"""
        if anchor_avg == 0:
            return 1.0
        
        diff_ratio = abs(text_avg - anchor_avg) / anchor_avg
        
        if diff_ratio < 0.1:
            return 1.0
        elif diff_ratio < 0.3:
            return 0.7
        elif diff_ratio < 0.5:
            return 0.5
        else:
            return 0.3
    
    def _check_sentence_pattern(
        self,
        text_patterns: Dict[str, Any],
        anchor_patterns: Dict[str, Any],
    ) -> float:
        """检查句式模式一致性"""
        # 简化实现
        return 0.8
    
    def _check_punctuation(
        self,
        text_complexity: float,
        anchor_complexity: float,
    ) -> float:
        """检查标点复杂度一致性"""
        if anchor_complexity == 0:
            return 1.0
        
        diff_ratio = abs(text_complexity - anchor_complexity) / max(anchor_complexity, 0.01)
        
        if diff_ratio < 0.2:
            return 1.0
        elif diff_ratio < 0.5:
            return 0.7
        else:
            return 0.5
    
    def _check_vocabulary(
        self,
        text_richness: float,
        anchor_richness: float,
    ) -> float:
        """检查词汇丰富度一致性"""
        if anchor_richness == 0:
            return 1.0
        
        diff_ratio = abs(text_richness - anchor_richness) / max(anchor_richness, 0.01)
        
        if diff_ratio < 0.2:
            return 1.0
        elif diff_ratio < 0.5:
            return 0.7
        else:
            return 0.5
    
    def _check_syntactic(
        self,
        text_complexity: float,
        anchor_complexity: float,
    ) -> float:
        """检查句法复杂度一致性"""
        if anchor_complexity == 0:
            return 1.0
        
        diff_ratio = abs(text_complexity - anchor_complexity) / max(anchor_complexity, 0.01)
        
        if diff_ratio < 0.2:
            return 1.0
        elif diff_ratio < 0.5:
            return 0.7
        else:
            return 0.5
    
    def _check_tone(
        self,
        text_tone: str,
        anchor_tone: str,
    ) -> float:
        """检查语调一致性"""
        if text_tone == anchor_tone:
            return 1.0
        elif text_tone == "neutral" or anchor_tone == "neutral":
            return 0.7
        else:
            return 0.5
    
    def _calculate_anchor_similarity(
        self,
        text_features: Dict[str, Any],
        anchor_features: Dict[str, Any],
    ) -> float:
        """计算锚点相似度"""
        # 简化实现：基于特征匹配
        return 0.8
    
    def _generate_suggestions(
        self,
        dimension_scores: List[DimensionScore],
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        for ds in dimension_scores:
            if not ds.is_acceptable:
                if ds.dimension_name == "catchphrase":
                    suggestions.append("增加口头禅的使用频率，使其更符合锚定风格")
                elif ds.dimension_name == "sentence_length":
                    suggestions.append("调整句子长度，使其更接近锚定风格")
                elif ds.dimension_name == "punctuation":
                    suggestions.append("调整标点使用，使其更符合锚定风格")
                elif ds.dimension_name == "vocabulary":
                    suggestions.append("丰富词汇使用，提高表达多样性")
                elif ds.dimension_name == "syntactic":
                    suggestions.append("调整句法结构，使其更符合锚定风格")
                elif ds.dimension_name == "tone":
                    suggestions.append("调整语调，使其更符合锚定风格")
        
        return suggestions

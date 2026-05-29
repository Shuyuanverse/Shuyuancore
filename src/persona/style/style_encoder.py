# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格编码器 — 从提取结果计算 7 维画像 + 风格类型分类。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

from .base import StyleExtractionResult


@dataclass
class StyleDimension:
    """单个风格维度。

    Attributes:
        name: 维度名称
        value: 维度值 (0-1)
        features: 该维度依赖的原始特征
        weight: 权重，默认 1.0
        description: 描述
    """

    name: str
    value: float
    features: Dict[str, float] = field(default_factory=dict)
    weight: float = 1.0
    description: str = ""


@dataclass
class StyleProfile:
    """7 维风格画像。

    Attributes:
        dimensions: 7 个风格维度
        overall_score: 整体评分
        style_type: 风格类型（6 种之一）
        confidence: 置信度 (0-1)
        raw_result: 原始提取结果
    """

    dimensions: Dict[str, StyleDimension]
    overall_score: float
    style_type: str
    confidence: float
    raw_result: Optional[StyleExtractionResult] = None


class StyleEncoder:
    """风格编码器 — 从提取结果计算 7 维画像。

    7 个维度：
    1. colloquial  口语化程度
    2. formal      正式程度
    3. emotional   情感表达
    4. interactive 互动风格
    5. logical     逻辑严谨
    6. concise     表达简洁
    7. expressive  表现力
    """

    STYLE_TYPES = {
        "academic_speech": "学术演讲",
        "knowledge_sharing": "知识分享",
        "casual_chat": "日常聊天",
        "emotional_sharing": "情感倾诉",
        "business_communication": "商务沟通",
        "creative_expression": "创意表达",
    }

    def encode(self, result: StyleExtractionResult) -> StyleProfile:
        """从风格提取结果编码为风格画像。

        Args:
            result: 风格提取结果

        Returns:
            StyleProfile: 7 维风格画像
        """
        dimensions = self._compute_dimensions(result)
        overall_score = self._calculate_overall_score(dimensions)
        style_type = self._classify_style_type(dimensions)
        confidence = self._calculate_confidence(dimensions, style_type)

        return StyleProfile(
            dimensions=dimensions,
            overall_score=overall_score,
            style_type=style_type,
            confidence=confidence,
            raw_result=result,
        )

    def _compute_dimensions(self, result: StyleExtractionResult) -> Dict[str, StyleDimension]:
        """计算 7 个风格维度。

        Args:
            result: 风格提取结果

        Returns:
            Dict[str, StyleDimension]: 7 个维度
        """
        catchphrases = result.catchphrases
        sentence_patterns = result.sentence_patterns
        punct_habits = result.punctuation_habits
        vocab_metrics = result.vocabulary_metrics
        syntactic_features = result.syntactic_features

        # colloquial（口语化） = 口头禅频率 * 0.35 + 短句比例 (<10 字) * 0.25 + 感叹句比例 * 0.20 + 口语标点 (！？～) 比例 * 0.20
        catchphrase_freq = sum(catchphrases.values()) if catchphrases else 0.0
        short_ratio = sentence_patterns.get("short", 0.0)
        exclamatory_ratio = sentence_patterns.get("exclamatory", 0.0)
        casual_punct = (
            punct_habits.get("！", 0.0) + punct_habits.get("！", 0.0) + punct_habits.get("～", 0.0)
        )
        colloquial = (
            catchphrase_freq * 0.35
            + short_ratio * 0.25
            + exclamatory_ratio * 0.20
            + casual_punct * 0.20
        )

        # formal（正式） = 词汇复杂度 (TTR*2) * 0.30 + 平均句长归一化 * 0.25 + 标点规范度 (句号逗号占比) * 0.25 + 从句比例 * 0.20
        ttr = vocab_metrics.get("ttr", 0.0)
        vocab_complexity = min(ttr * 2, 1.0)
        avg_word_len = vocab_metrics.get("avg_word_length", 0.0)
        avg_sent_length_norm = min(avg_word_len / 30.0, 1.0)
        standard_punct = punct_habits.get("。", 0.0) + punct_habits.get("，", 0.0)
        clause_ratio = syntactic_features.get("subordinate_ratio", 0.0)
        formal = (
            vocab_complexity * 0.30
            + avg_sent_length_norm * 0.25
            + standard_punct * 0.25
            + clause_ratio * 0.20
        )

        # emotional（情感表达） = 感叹句比例 * 0.30 + 感叹号频率 * 0.25 + 情感口头禅频率 * 0.25 + 标点复杂度 * 0.20
        punct_complexity = vocab_metrics.get("punctuation_complexity", 0.0)
        emotional_catchphrases = sum(
            freq
            for phrase, freq in catchphrases.items()
            if any(p in phrase for p in ["哇", "天", "妈", "命", "绝绝子", "yyds"])
        )
        emotional = (
            exclamatory_ratio * 0.30
            + punct_habits.get("！", 0.0) * 0.25
            + emotional_catchphrases * 0.25
            + punct_complexity * 0.20
        )

        # interactive（互动） = 疑问句比例 * 0.30 + 互动口头禅频率 * 0.25 + 问号频率 * 0.25 + 开场结尾模式频率 * 0.20
        interrogatory_ratio = sentence_patterns.get("interrogative", 0.0)
        interactive_catchphrases = sum(
            freq
            for phrase, freq in catchphrases.items()
            if any(p in phrase for p in ["加油", "冲", "牛", "厉害"])
        )
        question_punct = punct_habits.get("？", 0.0)
        opening_ending = sum(sentence_patterns.get(k, 0.0) for k in ["short", "medium"]) * 0.5
        interactive = (
            interrogatory_ratio * 0.30
            + interactive_catchphrases * 0.25
            + question_punct * 0.25
            + opening_ending * 0.20
        )

        # logical（逻辑） = 从句比例 * 0.30 + 长句比例 (>20 字) * 0.25 + 逗号使用频率 * 0.25 + 过渡词频率 * 0.20
        long_ratio = sentence_patterns.get("long", 0.0) + sentence_patterns.get("very_long", 0.0)
        comma_freq = punct_habits.get("，", 0.0)
        transition_words = sum(
            freq
            for phrase, freq in catchphrases.items()
            if any(
                p in phrase
                for p in ["然后", "接着", "另外", "不过", "但是", "而且", "所以", "因此"]
            )
        )
        logical = (
            clause_ratio * 0.30 + long_ratio * 0.25 + comma_freq * 0.25 + transition_words * 0.20
        )

        # concise（简洁） = 短句比例 * 0.30 + 简单标点比例 (。,) * 0.25 + Hapax 比率 * 0.25 + (1 - 平均句长归一化) * 0.20
        hapax_ratio = vocab_metrics.get("hapax_ratio", 0.0)
        simple_punct = punct_habits.get("。", 0.0) + punct_habits.get("，", 0.0)
        concise = (
            short_ratio * 0.30
            + simple_punct * 0.25
            + hapax_ratio * 0.25
            + (1.0 - avg_sent_length_norm) * 0.20
        )

        # expressive（表现力） = TTR * 0.25 + 句式多样性 (句子类型熵) * 0.25 + 标点多样性 (标点熵) * 0.25 + 修辞标记频率 * 0.25
        sentence_type_entropy = self._calculate_entropy(
            {
                "declarative": sentence_patterns.get("declarative", 0.0),
                "interrogative": sentence_patterns.get("interrogative", 0.0),
                "exclamatory": sentence_patterns.get("exclamatory", 0.0),
            }
        )
        punct_diversity = self._calculate_entropy(punct_habits)
        rhetorical_markers = sum(freq for phrase, freq in catchphrases.items() if len(phrase) >= 4)
        expressive = (
            ttr * 0.25
            + sentence_type_entropy * 0.25
            + punct_diversity * 0.25
            + rhetorical_markers * 0.25
        )

        return {
            "colloquial": StyleDimension(
                name="colloquial",
                value=min(max(colloquial, 0.0), 1.0),
                features={
                    "catchphrase_freq": catchphrase_freq,
                    "short_ratio": short_ratio,
                    "exclamatory_ratio": exclamatory_ratio,
                    "casual_punct": casual_punct,
                },
                description="口语化程度",
            ),
            "formal": StyleDimension(
                name="formal",
                value=min(max(formal, 0.0), 1.0),
                features={
                    "vocab_complexity": vocab_complexity,
                    "avg_sent_length_norm": avg_sent_length_norm,
                    "standard_punct": standard_punct,
                    "clause_ratio": clause_ratio,
                },
                description="正式程度",
            ),
            "emotional": StyleDimension(
                name="emotional",
                value=min(max(emotional, 0.0), 1.0),
                features={
                    "exclamatory_ratio": exclamatory_ratio,
                    "exclamation_freq": punct_habits.get("！", 0.0),
                    "emotional_catchphrases": emotional_catchphrases,
                    "punct_complexity": punct_complexity,
                },
                description="情感表达",
            ),
            "interactive": StyleDimension(
                name="interactive",
                value=min(max(interactive, 0.0), 1.0),
                features={
                    "interrogatory_ratio": interrogatory_ratio,
                    "interactive_catchphrases": interactive_catchphrases,
                    "question_punct": question_punct,
                    "opening_ending": opening_ending,
                },
                description="互动风格",
            ),
            "logical": StyleDimension(
                name="logical",
                value=min(max(logical, 0.0), 1.0),
                features={
                    "clause_ratio": clause_ratio,
                    "long_ratio": long_ratio,
                    "comma_freq": comma_freq,
                    "transition_words": transition_words,
                },
                description="逻辑严谨",
            ),
            "concise": StyleDimension(
                name="concise",
                value=min(max(concise, 0.0), 1.0),
                features={
                    "short_ratio": short_ratio,
                    "simple_punct": simple_punct,
                    "hapax_ratio": hapax_ratio,
                    "avg_sent_length_norm": avg_sent_length_norm,
                },
                description="表达简洁",
            ),
            "expressive": StyleDimension(
                name="expressive",
                value=min(max(expressive, 0.0), 1.0),
                features={
                    "ttr": ttr,
                    "sentence_type_entropy": sentence_type_entropy,
                    "punct_diversity": punct_diversity,
                    "rhetorical_markers": rhetorical_markers,
                },
                description="表现力",
            ),
        }

    def _calculate_overall_score(self, dimensions: Dict[str, StyleDimension]) -> float:
        """加权整体评分。

        Args:
            dimensions: 7 个维度

        Returns:
            float: 整体评分 (0-1)
        """
        total_weight = sum(dim.weight for dim in dimensions.values())
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(dim.value * dim.weight for dim in dimensions.values())
        return weighted_sum / total_weight

    def _classify_style_type(self, dimensions: Dict[str, StyleDimension]) -> str:
        """风格类型分类（根据 7 维最大值分配）。

        Args:
            dimensions: 7 个维度

        Returns:
            str: 风格类型 key
        """
        values = {name: dim.value for name, dim in dimensions.items()}

        if values.get("formal", 0) > 0.6 and values.get("logical", 0) > 0.6:
            return "academic_speech"
        elif values.get("formal", 0) > 0.5 and values.get("logical", 0) > 0.5:
            return "knowledge_sharing"
        elif values.get("colloquial", 0) > 0.6 and values.get("emotional", 0) > 0.5:
            return "casual_chat"
        elif values.get("emotional", 0) > 0.6 and values.get("interactive", 0) > 0.5:
            return "emotional_sharing"
        elif values.get("formal", 0) > 0.5 and values.get("concise", 0) > 0.5:
            return "business_communication"
        elif values.get("expressive", 0) > 0.6:
            return "creative_expression"
        else:
            return "casual_chat"

    def _calculate_confidence(
        self, dimensions: Dict[str, StyleDimension], style_type: str
    ) -> float:
        """计算分类置信度。

        Args:
            dimensions: 7 个维度
            style_type: 分类结果

        Returns:
            float: 置信度 (0-1)
        """
        values = [dim.value for dim in dimensions.values()]
        if not values:
            return 0.0

        max_val = max(values)
        second_max = sorted(values, reverse=True)[1] if len(values) > 1 else 0.0

        gap = max_val - second_max
        confidence = min(gap * 2 + 0.5, 1.0)

        return confidence

    def _calculate_entropy(self, distribution: Dict[str, float]) -> float:
        """计算分布的信息熵。

        Args:
            distribution: 概率分布

        Returns:
            float: 熵值 (0-1)
        """
        if not distribution:
            return 0.0

        entropy = 0.0
        for prob in distribution.values():
            if prob > 0:
                entropy -= prob * math.log2(prob)

        max_entropy = math.log2(len(distribution)) if len(distribution) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def calculate_style_match(self, profile_a: StyleProfile, profile_b: StyleProfile) -> float:
        """计算两个画像的匹配度。

        Args:
            profile_a: 画像 A
            profile_b: 画像 B

        Returns:
            float: 匹配度 (0-1)
        """
        if not profile_a.dimensions or not profile_b.dimensions:
            return 0.0

        total_diff = 0.0
        count = 0

        for name in profile_a.dimensions:
            if name in profile_b.dimensions:
                diff = abs(profile_a.dimensions[name].value - profile_b.dimensions[name].value)
                total_diff += diff
                count += 1

        if count == 0:
            return 0.0

        avg_diff = total_diff / count
        return 1.0 - avg_diff

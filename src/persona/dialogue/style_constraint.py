# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格约束编码 — 完整实现。

StyleFeatures → ConstraintVector
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class ConstraintType(Enum):
    """约束类型"""

    LEXICAL = "lexical"
    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    RHETORICAL = "rhetorical"
    TONAL = "tonal"
    STRUCTURAL = "structural"


@dataclass
class ConstraintDimension:
    """约束维度

    Attributes:
        name: 维度名称
        constraint_type: 约束类型
        target_value: 目标值
        weight: 权重 0-1
        strength: 强度 0-1
        enabled: 是否启用
    """

    name: str
    constraint_type: str
    target_value: Any
    weight: float = 1.0
    strength: float = 0.5
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "constraint_type": self.constraint_type,
            "target_value": self.target_value,
            "weight": self.weight,
            "strength": self.strength,
            "enabled": self.enabled,
        }


@dataclass
class ConstraintVector:
    """约束向量 — 生成时应遵循的风格约束

    Attributes:
        dimensions: 维度列表
        global_strength: 全局强度
        source_profile: 源画像
        vector_representation: 向量表示
    """

    dimensions: List[ConstraintDimension]
    global_strength: float = 0.5
    source_profile: Optional[str] = None
    vector_representation: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dimensions": [d.to_dict() for d in self.dimensions],
            "global_strength": self.global_strength,
            "source_profile": self.source_profile,
            "has_vector": self.vector_representation is not None,
        }


class StyleConstraintEncoder:
    """风格约束编码器 — StyleFeatures → ConstraintVector

    encode(style_features, global_strength) → ConstraintVector
    encode_from_text(text, global_strength) → ConstraintVector
    merge_constraints(constraints, weights) → ConstraintVector  # 合并多个约束
    """

    def __init__(self):
        """初始化风格约束编码器"""
        # 维度名映射
        self.dimension_names = [
            "catchphrase_freq",
            "sentence_length",
            "sentence_type",
            "punctuation_complexity",
            "vocabulary_richness",
            "syntactic_complexity",
            "sentence_opening",
            "sentence_ending",
            "tone_formality",
            "emoticon_usage",
        ]

        logger.info("[style_constraint] 编码器初始化完成")

    def encode(
        self,
        style_features: Dict[str, Any],
        global_strength: float = 0.5,
    ) -> ConstraintVector:
        """从风格特征编码约束向量

        Args:
            style_features: 风格特征字典
            global_strength: 全局强度

        Returns:
            ConstraintVector: 约束向量
        """
        dimensions = []

        # catchphrase_freq 维度
        if "catchphrase_freq" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="catchphrase_freq",
                    constraint_type=ConstraintType.LEXICAL.value,
                    target_value=style_features["catchphrase_freq"],
                    weight=1.2,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # sentence_length 维度
        if "sentence_length" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="sentence_length",
                    constraint_type=ConstraintType.STRUCTURAL.value,
                    target_value=style_features["sentence_length"],
                    weight=1.0,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # sentence_type 维度
        if "sentence_type" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="sentence_type",
                    constraint_type=ConstraintType.SYNTACTIC.value,
                    target_value=style_features["sentence_type"],
                    weight=0.9,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # punctuation_complexity 维度
        if "punctuation_complexity" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="punctuation_complexity",
                    constraint_type=ConstraintType.TONAL.value,
                    target_value=style_features["punctuation_complexity"],
                    weight=0.8,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # vocabulary_richness 维度
        if "vocabulary_richness" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="vocabulary_richness",
                    constraint_type=ConstraintType.LEXICAL.value,
                    target_value=style_features["vocabulary_richness"],
                    weight=0.7,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # syntactic_complexity 维度
        if "syntactic_complexity" in style_features:
            dimensions.append(
                ConstraintDimension(
                    name="syntactic_complexity",
                    constraint_type=ConstraintType.SYNTACTIC.value,
                    target_value=style_features["syntactic_complexity"],
                    weight=0.8,
                    strength=global_strength,
                    enabled=True,
                )
            )

        # 构建向量表示
        vector = self._build_vector(dimensions)

        constraint_vector = ConstraintVector(
            dimensions=dimensions,
            global_strength=global_strength,
            source_profile=style_features.get("source_profile"),
            vector_representation=vector,
        )

        logger.info(
            "[style_constraint] 编码完成：dimensions=%d, strength=%.2f",
            len(dimensions),
            global_strength,
        )

        return constraint_vector

    def encode_from_text(
        self,
        text: str,
        global_strength: float = 0.5,
    ) -> ConstraintVector:
        """从文本编码约束向量

        Args:
            text: 文本
            global_strength: 全局强度

        Returns:
            ConstraintVector: 约束向量
        """
        # 提取风格特征
        style_features = self._extract_features(text)

        # 编码
        return self.encode(style_features, global_strength)

    def merge_constraints(
        self,
        constraints: List[ConstraintVector],
        weights: Optional[List[float]] = None,
    ) -> ConstraintVector:
        """合并多个约束

        Args:
            constraints: 约束向量列表
            weights: 权重列表（可选）

        Returns:
            ConstraintVector: 合并后的约束向量
        """
        if not constraints:
            raise ValueError("约束列表不能为空")

        if len(constraints) == 1:
            return constraints[0]

        # 默认权重相等
        if weights is None:
            weights = [1.0 / len(constraints)] * len(constraints)

        # 合并维度
        merged_dimensions = []
        dimension_map: Dict[str, List[ConstraintDimension]] = {}

        for constraint in constraints:
            for dim in constraint.dimensions:
                if dim.name not in dimension_map:
                    dimension_map[dim.name] = []
                dimension_map[dim.name].append(dim)

        # 对每个维度取加权平均
        for dim_name, dims in dimension_map.items():
            if not dims:
                continue

            # 加权平均 target_value
            target_values = [
                d.target_value for d in dims if isinstance(d.target_value, (int, float))
            ]
            if target_values:
                avg_target = sum(
                    t * w for t, w in zip(target_values, weights[: len(target_values)])
                )
            else:
                avg_target = dims[0].target_value

            # 加权平均 weight
            avg_weight = sum(d.weight * w for d, w in zip(dims, weights))

            # 取最大 strength
            max_strength = max(d.strength for d in dims)

            merged_dim = ConstraintDimension(
                name=dim_name,
                constraint_type=dims[0].constraint_type,
                target_value=avg_target,
                weight=avg_weight,
                strength=max_strength,
                enabled=all(d.enabled for d in dims),
            )
            merged_dimensions.append(merged_dim)

        # 构建向量表示
        vector = self._build_vector(merged_dimensions)

        # 全局强度取平均
        avg_global_strength = sum(c.global_strength * w for c, w in zip(constraints, weights))

        merged_vector = ConstraintVector(
            dimensions=merged_dimensions,
            global_strength=avg_global_strength,
            source_profile=f"merged_{len(constraints)}_constraints",
            vector_representation=vector,
        )

        logger.info(
            "[style_constraint] 合并完成：constraints=%d, merged_dimensions=%d",
            len(constraints),
            len(merged_dimensions),
        )

        return merged_vector

    def _extract_features(self, text: str) -> Dict[str, Any]:
        """从文本提取风格特征

        Args:
            text: 文本

        Returns:
            Dict: 风格特征字典
        """
        # 句子分割
        sentences = text.split("。")
        sentences = [s for s in sentences if s.strip()]

        # 平均句子长度
        avg_sentence_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0

        # 标点复杂度
        punctuation_count = (
            text.count("，") + text.count("。") + text.count("！") + text.count("？")
        )
        punctuation_complexity = punctuation_count / max(len(text), 1)

        # 词汇丰富度
        words = text.replace("。", " ").replace("，", " ").split()
        unique_words = set(words)
        vocabulary_richness = len(unique_words) / max(len(words), 1)

        # 句法复杂度
        syntactic_complexity = 1.0 if avg_sentence_length > 30 else 0.5

        # 语调正式度
        formal_words = ["您", "请", "贵", "敬语"]
        informal_words = ["咱", "俺", "啥", "咋"]
        formal_count = sum(1 for word in formal_words if word in text)
        informal_count = sum(1 for word in informal_words if word in text)
        tone_formality = formal_count / max(formal_count + informal_count, 1)

        return {
            "sentence_length": avg_sentence_length,
            "punctuation_complexity": punctuation_complexity,
            "vocabulary_richness": vocabulary_richness,
            "syntactic_complexity": syntactic_complexity,
            "tone_formality": tone_formality,
            "catchphrase_freq": 0.5,  # 简化
            "sentence_type": "mixed",  # 简化
            "sentence_opening": "diverse",  # 简化
            "sentence_ending": "varied",  # 简化
            "emoticon_usage": 0.0,  # 简化
        }

    def _build_vector(
        self,
        dimensions: List[ConstraintDimension],
    ) -> np.ndarray:
        """构建向量表示

        Args:
            dimensions: 维度列表

        Returns:
            np.ndarray: 向量
        """
        if not dimensions:
            return np.zeros(10)

        # 提取目标值和权重
        values = []
        weights = []

        for dim in dimensions:
            if isinstance(dim.target_value, (int, float)):
                values.append(dim.target_value)
                weights.append(dim.weight)

        if not values:
            return np.zeros(10)

        # 加权值
        weighted_values = np.array(values) * np.array(weights)

        # 扩展到 10 维
        if len(weighted_values) < 10:
            vector = np.zeros(10)
            vector[: len(weighted_values)] = weighted_values
        else:
            vector = weighted_values[:10]

        return vector

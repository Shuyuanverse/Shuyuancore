# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格向量生成器 — 从 StyleExtractionResult + StyleProfile 生成 60 维风格向量。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .base import StyleExtractionResult
from .style_encoder import StyleProfile


@dataclass
class StyleVector:
    """60 维风格向量。

    Attributes:
        vector: 60 维 numpy 数组
        dimension_names: 60 个维度名称
        cosine_similarity: 余弦相似度（计算后填充）
        euclidean_distance: 欧氏距离（计算后填充）
    """

    vector: np.ndarray
    dimension_names: List[str]
    cosine_similarity: float = 0.0
    euclidean_distance: float = 0.0


class StyleVectorGenerator:
    """风格向量生成器。

    60 维分布：
    - 词汇维度 (0-9): vocab_richness, vocab_size_norm, hapax_ratio, avg_word_length,
                      word_freq_entropy, content_word_ratio, function_word_ratio,
                      rare_word_ratio, neologism_ratio, loanword_ratio
    - 句式维度 (10-19): sentence_length_mean, short_sentence_ratio, long_sentence_ratio,
                        sentence_length_variance, declarative_ratio, interrogative_ratio,
                        exclamatory_ratio, sentence_opening_diversity, sentence_ending_diversity,
                        avg_clause_count
    - 标点维度 (20-29): period_ratio, comma_ratio, question_ratio, exclamation_ratio,
                        colon_ratio, semicolon_ratio, dash_ratio, ellipsis_ratio,
                        bracket_ratio, punctuation_diversity
    - 句法维度 (30-39): syntactic_complexity, clause_density, subordinate_ratio,
                        coordination_ratio, nesting_depth, sentence_type_entropy,
                        pattern_consistency, transition_word_ratio, opening_pattern_strength,
                        ending_pattern_strength
    - 风格维度 (40-49): colloquial_score, formal_score, emotional_score,
                        interactive_score, logical_score, concise_score,
                        expressive_score, style_consistency, type_confidence,
                        overall_complexity
    - 综合维度 (50-59): overall_complexity, information_density, coherence_score,
                        redundancy_ratio, creativity_index, emotional_valence,
                        engagement_score, readability_score, uniqueness_score,
                        style_stability
    """

    DIMENSION_NAMES = [
        "vocab_richness",
        "vocab_size_norm",
        "hapax_ratio",
        "avg_word_length",
        "word_freq_entropy",
        "content_word_ratio",
        "function_word_ratio",
        "rare_word_ratio",
        "neologism_ratio",
        "loanword_ratio",
        "sentence_length_mean",
        "short_sentence_ratio",
        "long_sentence_ratio",
        "sentence_length_variance",
        "declarative_ratio",
        "interrogative_ratio",
        "exclamatory_ratio",
        "sentence_opening_diversity",
        "sentence_ending_diversity",
        "avg_clause_count",
        "period_ratio",
        "comma_ratio",
        "question_ratio",
        "exclamation_ratio",
        "colon_ratio",
        "semicolon_ratio",
        "dash_ratio",
        "ellipsis_ratio",
        "bracket_ratio",
        "punctuation_diversity",
        "syntactic_complexity",
        "clause_density",
        "subordinate_ratio",
        "coordination_ratio",
        "nesting_depth",
        "sentence_type_entropy",
        "pattern_consistency",
        "transition_word_ratio",
        "opening_pattern_strength",
        "ending_pattern_strength",
        "colloquial_score",
        "formal_score",
        "emotional_score",
        "interactive_score",
        "logical_score",
        "concise_score",
        "expressive_score",
        "style_consistency",
        "type_confidence",
        "overall_complexity",
        "complexity_index",
        "information_density",
        "coherence_score",
        "redundancy_ratio",
        "creativity_index",
        "emotional_valence",
        "engagement_score",
        "readability_score",
        "uniqueness_score",
        "style_stability",
    ]

    def generate(
        self, result: StyleExtractionResult, profile: StyleProfile | None = None
    ) -> StyleVector:
        """从风格提取结果生成 60 维向量。

        Args:
            result: 风格提取结果
            profile: 可选的风格画像（如有则填充风格维度）

        Returns:
            StyleVector: 60 维风格向量
        """
        vector = self._build_vector(result, profile)
        vector = self._normalize_vector(vector)

        return StyleVector(
            vector=vector,
            dimension_names=self.DIMENSION_NAMES,
        )

    def _build_vector(
        self, result: StyleExtractionResult, profile: StyleProfile | None
    ) -> np.ndarray:
        """从提取结果和画像构建 60 维向量。

        Args:
            result: 风格提取结果
            profile: 可选的风格画像

        Returns:
            np.ndarray: 60 维向量
        """
        vec = np.zeros(60, dtype=np.float32)

        vocab_metrics = result.vocabulary_metrics
        sentence_patterns = result.sentence_patterns
        punct_habits = result.punctuation_habits
        syntactic_features = result.syntactic_features

        vec[0] = vocab_metrics.get("ttr", 0.0)
        vec[1] = min(result.num_words / 1000.0, 1.0)
        vec[2] = vocab_metrics.get("hapax_ratio", 0.0)
        vec[3] = min(vocab_metrics.get("avg_word_length", 0.0) / 10.0, 1.0)
        vec[4] = self._calculate_word_freq_entropy(result.raw_features.get("word_freq", {}))
        vec[5] = 0.5
        vec[6] = 0.5
        vec[7] = 0.3
        vec[8] = 0.2
        vec[9] = 0.1

        lengths = [len(s) for s in result.raw_features.get("sentences", [])]
        if lengths:
            vec[10] = sum(lengths) / len(lengths) / 50.0
            vec[11] = sentence_patterns.get("short", 0.0)
            vec[12] = sentence_patterns.get("long", 0.0) + sentence_patterns.get("very_long", 0.0)
            if len(lengths) > 1:
                mean_len = sum(lengths) / len(lengths)
                variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
                vec[13] = min(variance / 100.0, 1.0)
        vec[14] = sentence_patterns.get("declarative", 0.0)
        vec[15] = sentence_patterns.get("interrogative", 0.0)
        vec[16] = sentence_patterns.get("exclamatory", 0.0)
        vec[17] = len([k for k in sentence_patterns if "opening" in k]) / 10.0
        vec[18] = len([k for k in sentence_patterns if "ending" in k]) / 10.0
        vec[19] = min(syntactic_features.get("syntactic_complexity", 0.0) * 5, 1.0)

        vec[20] = punct_habits.get("。", 0.0)
        vec[21] = punct_habits.get("，", 0.0)
        vec[22] = punct_habits.get("？", 0.0)
        vec[23] = punct_habits.get("！", 0.0)
        vec[24] = punct_habits.get("：", 0.0)
        vec[25] = punct_habits.get("；", 0.0)
        vec[26] = punct_habits.get("—", 0.0)
        vec[27] = punct_habits.get("……", 0.0)
        vec[28] = punct_habits.get("（", 0.0) + punct_habits.get("）", 0.0)
        vec[29] = vocab_metrics.get("punctuation_complexity", 0.0)

        vec[30] = syntactic_features.get("syntactic_complexity", 0.0)
        vec[31] = min(syntactic_features.get("subordinate_ratio", 0.0) * 2, 1.0)
        vec[32] = syntactic_features.get("subordinate_ratio", 0.0)
        vec[33] = 0.3
        vec[34] = 0.2
        vec[35] = self._calculate_sentence_type_entropy(sentence_patterns)
        vec[36] = 0.5
        vec[37] = sum(result.catchphrases.values()) if result.catchphrases else 0.0
        vec[38] = len(sentence_patterns.get("opening", {})) / 10.0
        vec[39] = len(sentence_patterns.get("ending", {})) / 10.0

        if profile:
            vec[40] = (
                profile.dimensions.get("colloquial", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("colloquial", None), "value")
                else 0.5
            )
            vec[41] = (
                profile.dimensions.get("formal", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("formal", None), "value")
                else 0.5
            )
            vec[42] = (
                profile.dimensions.get("emotional", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("emotional", None), "value")
                else 0.5
            )
            vec[43] = (
                profile.dimensions.get("interactive", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("interactive", None), "value")
                else 0.5
            )
            vec[44] = (
                profile.dimensions.get("logical", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("logical", None), "value")
                else 0.5
            )
            vec[45] = (
                profile.dimensions.get("concise", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("concise", None), "value")
                else 0.5
            )
            vec[46] = (
                profile.dimensions.get("expressive", type("obj", (object,), {"value": 0})()).value
                if hasattr(profile.dimensions.get("expressive", None), "value")
                else 0.5
            )
            vec[47] = 0.7
            vec[48] = profile.confidence
            vec[49] = profile.overall_score

        vec[50] = profile.overall_score if profile else 0.5
        vec[51] = (vec[0] + vec[2] + vec[4]) / 3
        vec[52] = 0.6
        vec[53] = 1.0 - vec[2]
        vec[54] = (vec[4] + vec[29] + vec[35]) / 3
        vec[55] = (vec[16] + vec[23] + vec[42]) / 3
        vec[56] = (vec[15] + vec[22] + vec[43]) / 3
        vec[57] = 1.0 - (vec[10] + vec[13]) / 2
        vec[58] = 1.0 - self._calculate_profile_consistency(profile) if profile else 0.5
        vec[59] = 0.7

        return vec

    def _normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """L2 归一化。

        Args:
            vec: 输入向量

        Returns:
            np.ndarray: 归一化后的向量
        """
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    def compute_similarity(
        self, vec_a: np.ndarray, vec_b: np.ndarray, method: str = "cosine"
    ) -> Tuple[float, float]:
        """多指标相似度计算（余弦 + 欧氏）。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B
            method: 方法（目前返回两种）

        Returns:
            Tuple[float, float]: (余弦相似度，欧氏距离)
        """
        dot_product = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        if norm_a > 0 and norm_b > 0:
            cosine_sim = dot_product / (norm_a * norm_b)
        else:
            cosine_sim = 0.0

        euclidean_dist = np.linalg.norm(vec_a - vec_b)

        return float(cosine_sim), float(euclidean_dist)

    def blend_vectors(self, vectors: List[np.ndarray], weights: List[float]) -> StyleVector:
        """风格向量混合（加权平均后归一化）。

        Args:
            vectors: 向量列表
            weights: 权重列表

        Returns:
            StyleVector: 混合后的向量
        """
        if not vectors or not weights:
            return StyleVector(
                vector=np.zeros(60),
                dimension_names=self.DIMENSION_NAMES,
            )

        total_weight = sum(weights)
        if total_weight == 0:
            weights = [1.0 / len(vectors)] * len(vectors)
            total_weight = 1.0

        blended = np.zeros(60)
        for vec, weight in zip(vectors, weights):
            blended += vec * (weight / total_weight)

        blended = self._normalize_vector(blended)

        return StyleVector(
            vector=blended,
            dimension_names=self.DIMENSION_NAMES,
        )

    def _calculate_word_freq_entropy(self, word_freq: dict) -> float:
        """计算词频熵。

        Args:
            word_freq: 词频字典

        Returns:
            float: 熵值 (0-1)
        """
        import math

        if not word_freq:
            return 0.0

        total = sum(word_freq.values())
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in word_freq.values():
            if count > 0:
                prob = count / total
                entropy -= prob * math.log2(prob)

        max_entropy = math.log2(len(word_freq)) if len(word_freq) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _calculate_sentence_type_entropy(self, sentence_patterns: dict) -> float:
        """计算句子类型熵。

        Args:
            sentence_patterns: 句式模式字典

        Returns:
            float: 熵值 (0-1)
        """
        import math

        types = ["declarative", "interrogative", "exclamatory"]
        probs = [sentence_patterns.get(t, 0.0) for t in types]
        probs = [p for p in probs if p > 0]

        if not probs:
            return 0.0

        entropy = -sum(p * math.log2(p) for p in probs)
        max_entropy = math.log2(len(probs)) if len(probs) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _calculate_profile_consistency(self, profile: StyleProfile) -> float:
        """计算画像一致性。

        Args:
            profile: 风格画像

        Returns:
            float: 一致性得分 (0-1)
        """
        if not profile.dimensions:
            return 0.5

        values = [dim.value for dim in profile.dimensions.values()]
        if len(values) < 2:
            return 0.5

        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)

        return min(variance * 4, 1.0)

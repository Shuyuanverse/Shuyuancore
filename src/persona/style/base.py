# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格编码系统基础定义。

本模块定义了风格编码系统的核心数据结构和接口。
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class StyleFeatureType(str, enum.Enum):
    """11 种特征类型枚举"""

    VOCABULARY_RICHNESS = "vocabulary_richness"
    CATCHPHRASE = "catchphrase"
    WORD_FREQUENCY = "word_frequency"
    SENTENCE_STRUCTURE = "sentence_structure"
    SENTENCE_LENGTH = "sentence_length"
    SYNTACTIC_COMPLEXITY = "syntactic_complexity"
    PUNCTUATION_HABIT = "punctuation_habit"
    PUNCTUATION_FREQUENCY = "punctuation_frequency"
    EMOTIONAL_TONE = "emotional_tone"
    INTERACTIVE_STYLE = "interactive_style"
    FORMALITY_LEVEL = "formality_level"
    OVERALL_STYLE = "overall_style"


@dataclass
class StyleConfig:
    """风格配置类。

    Attributes:
        catchphrase_threshold: 口头禅频率阈值，默认 0.3
        min_catchphrase_length: 口头禅最小长度，默认 2
        max_catchphrase_length: 口头禅最大长度，默认 8
        min_catchphrase_count: 最小口头禅数量，默认 2
        sentence_length_bins: 句子长度分箱，默认 (10, 20, 30, 50)
        max_vocabulary_size: 最大词汇表大小，默认 10000
        min_word_frequency: 最小词频，默认 2
        vector_dim: 向量维度，默认 128
        use_semantic_embedding: 是否使用语义嵌入，默认 True
        embedding_model: 嵌入模型名称，默认 "bert-base-chinese"
        transformers_available: transformers 库是否可用，运行时检测
        sklearn_available: sklearn 库是否可用，运行时检测
        jieba_available: jieba 库是否可用，运行时检测
    """

    catchphrase_threshold: float = 0.3
    min_catchphrase_length: int = 2
    max_catchphrase_length: int = 8
    min_catchphrase_count: int = 2
    sentence_length_bins: tuple = (10, 20, 30, 50)
    max_vocabulary_size: int = 10000
    min_word_frequency: int = 2
    vector_dim: int = 128
    use_semantic_embedding: bool = True
    embedding_model: str = "bert-base-chinese"
    transformers_available: bool = False
    sklearn_available: bool = False
    jieba_available: bool = False

    def __post_init__(self) -> None:
        """运行时依赖检测"""
        try:
            import jieba  # noqa: F401

            object.__setattr__(self, "jieba_available", True)
        except ImportError:
            pass

        try:
            import sklearn  # noqa: F401

            object.__setattr__(self, "sklearn_available", True)
        except ImportError:
            pass

        try:
            import transformers  # noqa: F401

            object.__setattr__(self, "transformers_available", True)
        except ImportError:
            pass


@dataclass
class StyleExtractionResult:
    """风格提取结果。

    Attributes:
        catchphrases: 口头禅→频率字典
        sentence_patterns: 句式模式→频率字典
        punctuation_habits: 标点习惯→频率字典
        vocabulary_metrics: 词汇指标（TTR、Hapax 比率、平均词长等）
        syntactic_features: 句法特征（从句比例、复杂度等）
        raw_features: 原始特征（句子列表、分词结果等）
        num_sentences: 句子数量
        num_words: 词语数量
        total_chars: 总字符数
    """

    catchphrases: Dict[str, float] = field(default_factory=dict)
    sentence_patterns: Dict[str, float] = field(default_factory=dict)
    punctuation_habits: Dict[str, float] = field(default_factory=dict)
    vocabulary_metrics: Dict[str, float] = field(default_factory=dict)
    syntactic_features: Dict[str, float] = field(default_factory=dict)
    raw_features: Dict[str, Any] = field(default_factory=dict)
    num_sentences: int = 0
    num_words: int = 0
    total_chars: int = 0


class BaseStyleExtractor(ABC):
    """风格提取器基类。"""

    @abstractmethod
    def extract(self, text: str) -> StyleExtractionResult:
        """从文本中提取风格特征。

        Args:
            text: 输入文本

        Returns:
            StyleExtractionResult: 风格提取结果
        """
        pass

    def extract_async(self, text: str) -> StyleExtractionResult:
        """异步版本（默认同步实现）。

        Args:
            text: 输入文本

        Returns:
            StyleExtractionResult: 风格提取结果
        """
        return self.extract(text)

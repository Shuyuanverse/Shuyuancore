# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""决策锚点系统 — 完整三路融合架构。

包含：
- 基础定义（枚举、配置、锚点类、版本管理、相似度计算）
- 决策编码器（BERT+ 三路融合 + NumPy 降级）
- 锚点管理（Wasserstein 漂移检测、版本管理、相似度服务）
- 25 维价值观定义
- LLM 语义翻译器
- 价值观↔向量双向映射
- 调整历史持久化
"""

from __future__ import annotations

from .adjustment_history import (
    AdjustmentHistory,
    AdjustmentRecord,
    ReviewResult,
    TriggerType,
)
from .anchor_manager import (
    AnchorSimilarityService,
    AnchorVersionManager,
    FeedbackSample,
    WassersteinDriftDetector,
)
from .base import (
    AnchorBase,
    AnchorConfig,
    AnchorStatus,
    AnchorType,
    AnchorVersion,
    DecisionAnchor,
    DriftLevel,
    SimilarityCalculator,
    StyleAnchor,
    generate_anchor_id,
    validate_vector_dimension,
)
from .bidirectional_mapping import (
    MAX_CUMULATIVE_ADJUSTMENT,
    MAX_DRIFT_SCORE,
    MAX_SINGLE_ADJUSTMENT,
    AdjustmentResult,
    AdjustmentSnapshot,
    BidirectionalMapper,
)
from .decision_anchor import (
    TORCH_AVAILABLE,
    DecisionAnchorManager,
    DecisionEncoder,
    DecisionEncoderLight,
)
from .semantic_translator import SemanticTranslator
from .value_dimensions import (
    ValueDimension,
    ValueDimensionsRegistry,
    ValueRange,
)

__all__ = [
    # Base
    "AnchorBase",
    "AnchorConfig",
    "AnchorStatus",
    "AnchorType",
    "AnchorVersion",
    "DecisionAnchor",
    "DriftLevel",
    "SimilarityCalculator",
    "StyleAnchor",
    "generate_anchor_id",
    "validate_vector_dimension",
    # Decision Anchor
    "DecisionAnchorManager",
    "DecisionEncoder",
    "DecisionEncoderLight",
    "TORCH_AVAILABLE",
    # Anchor Manager
    "AnchorSimilarityService",
    "AnchorVersionManager",
    "FeedbackSample",
    "WassersteinDriftDetector",
    # Value Dimensions
    "ValueDimension",
    "ValueDimensionsRegistry",
    "ValueRange",
    # Semantic Translator
    "SemanticTranslator",
    # Bidirectional Mapping
    "AdjustmentResult",
    "AdjustmentSnapshot",
    "BidirectionalMapper",
    "MAX_CUMULATIVE_ADJUSTMENT",
    "MAX_DRIFT_SCORE",
    "MAX_SINGLE_ADJUSTMENT",
    # Adjustment History
    "AdjustmentHistory",
    "AdjustmentRecord",
    "ReviewResult",
    "TriggerType",
]

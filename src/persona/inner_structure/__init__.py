# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""内心结构层 — 审视与自检。

包含：
- SelfReviewLayer：自审视层（4 维度评估）
- InnerStructurePipeline：内心结构管线（审视→调整建议）
"""

from __future__ import annotations

from .self_review import (
    ADJUST_THRESHOLD,
    AI_TEMPLATE_PATTERNS,
    EMERGENCY_THRESHOLD,
    FACT_ASSERTION_PATTERNS,
    PRIVATE_TOPIC_PATTERNS,
    WEIGHTS,
    SelfReviewLayer,
    SelfReviewResult,
)
from .pipeline import (
    AdjustmentSuggestion,
    InnerStructureConfig,
    InnerStructurePipeline,
    InnerStructureResult,
)

__all__ = [
    # Self Review
    "ADJUST_THRESHOLD",
    "AI_TEMPLATE_PATTERNS",
    "EMERGENCY_THRESHOLD",
    "FACT_ASSERTION_PATTERNS",
    "PRIVATE_TOPIC_PATTERNS",
    "WEIGHTS",
    "SelfReviewLayer",
    "SelfReviewResult",
    # Pipeline
    "AdjustmentSuggestion",
    "InnerStructureConfig",
    "InnerStructurePipeline",
    "InnerStructureResult",
]

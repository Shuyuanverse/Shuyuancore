# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""内心反应层 — 纯规则感知与反应。

包含：
- PerceptionEngine：纯规则感知引擎（零 LLM 调用）
- InnerReactionBuilder：内心反应构建器
- InnerReactionPipeline：内心反应管线编排
- PersonaSynergyBus：人格感知总线
"""
from __future__ import annotations

from .perception import (
    ATMOSPHERE_KEYWORDS,
    IDENTITY_CONFUSION_PATTERNS,
    USER_EMOTION_KEYWORDS,
    PerceptionEngine,
    PerceptionResult,
    REPEAT_SIMILARITY_THRESHOLD,
    PATIENCE_DECAY_PER_REPEAT,
    PATIENCE_DECAY_PER_NEGATIVE,
    WOLF_THRESHOLD,
)
from .reaction import (
    InnerReaction,
    InnerReactionBuilder,
)
from .pipeline import (
    InnerReactionConfig,
    InnerReactionPipeline,
    InnerReactionResult,
)
from .persona_synergy_bus import (
    InnerIntent,
    PersonaSynergyBus,
    PreConsciousSignal,
    SynergyBusResult,
)

__all__ = [
    # Perception
    "ATMOSPHERE_KEYWORDS",
    "IDENTITY_CONFUSION_PATTERNS",
    "USER_EMOTION_KEYWORDS",
    "PerceptionEngine",
    "PerceptionResult",
    "REPEAT_SIMILARITY_THRESHOLD",
    "PATIENCE_DECAY_PER_REPEAT",
    "PATIENCE_DECAY_PER_NEGATIVE",
    "WOLF_THRESHOLD",
    # Reaction
    "InnerReaction",
    "InnerReactionBuilder",
    # Pipeline
    "InnerReactionConfig",
    "InnerReactionPipeline",
    "InnerReactionResult",
    # Synergy Bus
    "InnerIntent",
    "PersonaSynergyBus",
    "PreConsciousSignal",
    "SynergyBusResult",
]

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格编码系统。

完整的四层管线：文本分析→7 维画像→60 维向量→128 维锚点
"""

from __future__ import annotations

from .base import (
    BaseStyleExtractor,
    StyleConfig,
    StyleExtractionResult,
    StyleFeatureType,
)
from .text_style import TextStyleAnalyzer
from .style_encoder import StyleDimension, StyleEncoder, StyleProfile
from .style_vector import StyleVector, StyleVectorGenerator
from .style_anchor import (
    StyleAnchor,
    StyleAnchorEncoder,
    StyleAnchorManager,
    extract_style_from_text,
    TORCH_AVAILABLE,
)

__all__ = [
    "BaseStyleExtractor",
    "StyleConfig",
    "StyleExtractionResult",
    "StyleFeatureType",
    "TextStyleAnalyzer",
    "StyleDimension",
    "StyleEncoder",
    "StyleProfile",
    "StyleVector",
    "StyleVectorGenerator",
    "StyleAnchor",
    "StyleAnchorEncoder",
    "StyleAnchorManager",
    "extract_style_from_text",
    "TORCH_AVAILABLE",
]

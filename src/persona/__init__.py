# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""人格编译与风格保护模块。"""

from __future__ import annotations

from .profile import PersonaProfile, StyleDimensions
from .style import (
    TORCH_AVAILABLE,
    BaseStyleExtractor,
    StyleAnchor,
    StyleAnchorEncoder,
    StyleAnchorManager,
    StyleConfig,
    StyleDimension,
    StyleEncoder,
    StyleExtractionResult,
    StyleFeatureType,
    StyleProfile,
    StyleVector,
    StyleVectorGenerator,
    TextStyleAnalyzer,
    extract_style_from_text,
)

__all__ = [
    "PersonaProfile",
    "StyleDimensions",
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

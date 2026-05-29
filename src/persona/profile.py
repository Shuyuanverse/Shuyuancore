from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .style.style_encoder import StyleProfile


@dataclass
class StyleDimensions:
    """风格 7 维度 — 最终定义"""

    colloquial: float = 0.5  # 口语化程度
    formal: float = 0.5  # 正式程度
    emotional: float = 0.5  # 情感表达
    interactive: float = 0.5  # 互动风格
    logical: float = 0.5  # 逻辑严谨
    concise: float = 0.5  # 表达简洁
    expressive: float = 0.5  # 表现力

    def to_vector(self) -> list[float]:
        return [
            self.colloquial,
            self.formal,
            self.emotional,
            self.interactive,
            self.logical,
            self.concise,
            self.expressive,
        ]

    def to_prompt_text(self) -> str:
        labels = {
            "口语化程度": self.colloquial,
            "正式程度": self.formal,
            "情感表达": self.emotional,
            "互动风格": self.interactive,
            "逻辑严谨": self.logical,
            "表达简洁": self.concise,
            "表现力": self.expressive,
        }
        lines = ["- " + k + "：" + str(round(v * 10, 1)) + "/10" for k, v in labels.items()]
        return "请保持以下风格特征（1-10）：\n" + "\n".join(lines)

    @classmethod
    def from_style_profile(cls, profile: StyleProfile) -> StyleDimensions:
        """从 StyleProfile 转换"""
        from .style.style_encoder import StyleDimension

        def get_value(name: str) -> float:
            dim = profile.dimensions.get(name)
            if dim and isinstance(dim, StyleDimension):
                return dim.value
            return 0.0

        return cls(
            colloquial=get_value("colloquial"),
            formal=get_value("formal"),
            emotional=get_value("emotional"),
            interactive=get_value("interactive"),
            logical=get_value("logical"),
            concise=get_value("concise"),
            expressive=get_value("expressive"),
        )


@dataclass
class PersonaProfile:
    persona_id: str
    mode: str
    style_dimensions: StyleDimensions
    style_anchor_vector: Optional[list[float]] = None  # 128 维
    decision_anchor_vector: Optional[list[float]] = None  # 256 维
    style_vector: Optional[list[float]] = None  # 60 维（新增）
    anchor_version: Optional[str] = None  # 锚点版本 ID（新增）
    values_profile: dict[str, float] = field(default_factory=dict)  # 25 维价值观（新增）
    hard_fact_belief_ids: list[str] = field(default_factory=list)
    language_samples: list[str] = field(default_factory=list)
    boundary_rules: list[str] = field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

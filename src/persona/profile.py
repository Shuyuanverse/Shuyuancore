from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StyleDimensions:
    formality: float = 0.5
    warmth: float = 0.5
    directness: float = 0.5
    playfulness: float = 0.5
    detail_orientation: float = 0.5
    emotional_expression: float = 0.5
    pace: float = 0.5

    def to_vector(self) -> list[float]:
        return [
            self.formality,
            self.warmth,
            self.directness,
            self.playfulness,
            self.detail_orientation,
            self.emotional_expression,
            self.pace,
        ]

    def to_prompt_text(self) -> str:
        labels = {
            "正式度": self.formality,
            "温暖度": self.warmth,
            "直接度": self.directness,
            "趣味度": self.playfulness,
            "细节取向度": self.detail_orientation,
            "情感表达度": self.emotional_expression,
            "节奏度": self.pace,
        }
        lines = ["- " + k + "：" + str(round(v * 10, 1)) + "/10" for k, v in labels.items()]
        return "请保持以下风格特征（1-10）：\n" + "\n".join(lines)


@dataclass
class PersonaProfile:
    persona_id: str
    mode: str
    style_dimensions: StyleDimensions
    style_anchor_vector: Optional[list[float]] = None
    decision_anchor_vector: Optional[list[float]] = None
    hard_fact_belief_ids: list[str] = field(default_factory=list)
    language_samples: list[str] = field(default_factory=list)
    boundary_rules: list[str] = field(default_factory=list)
    values_profile: dict[str, float] = field(default_factory=dict)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

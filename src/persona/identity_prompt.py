from __future__ import annotations
from typing import Optional
from src.persona.profile import PersonaProfile


class IdentityPromptBuilder:
    def __init__(self, profile: Optional[PersonaProfile] = None):
        self._profile = profile

    def set_profile(self, profile: PersonaProfile) -> None:
        self._profile = profile

    def build(self, profile: Optional[PersonaProfile] = None) -> str:
        p = profile or self._profile
        if p is None:
            return ""
        parts = [f"【人格标识】{p.persona_id} 模式：{p.mode}"]

        if p.style_dimensions:
            parts.append("")
            parts.append(p.style_dimensions.to_prompt_text())

        if p.boundary_rules:
            parts.append("")
            parts.append("边界规则：")
            for rule in p.boundary_rules:
                parts.append(f"- {rule}")

        if p.values_profile:
            parts.append("")
            parts.append("价值取向：")
            for key, val in sorted(p.values_profile.items(), key=lambda x: -x[1]):
                parts.append(f"- {key}：{val:.1f}/10")

        return "\n".join(parts)
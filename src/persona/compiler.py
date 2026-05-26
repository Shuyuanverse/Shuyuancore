from __future__ import annotations
from src.persona.profile import PersonaProfile, StyleDimensions
from src.persona.style_encoder import StyleEncoder
from src.persona.anchor_manager import AnchorManager
from src.persona.identity_prompt import IdentityPromptBuilder
from src.persona.hard_fact_guard import HardFactGuard


class PersonaCompiler:
    def __init__(
        self,
        anchor_manager: AnchorManager,
        style_encoder: StyleEncoder,
        hard_fact_guard: HardFactGuard,
    ):
        self._anchor_manager = anchor_manager
        self._style_encoder = style_encoder
        self._hard_fact_guard = hard_fact_guard

    async def compile_generic(
        self,
        persona_id: str,
        conversation_samples: list[str],
        core_md: str = "",
    ) -> PersonaProfile:
        combined = "\n".join(conversation_samples)
        style_dim = self._style_encoder.encode(combined)
        anchor = await self._anchor_manager.create_initial_anchor(persona_id, style_dim, combined)

        hard_fact_ids: list[str] = []
        if core_md.strip():
            hard_fact_ids = await self._hard_fact_guard.extract_from_core_md(core_md, persona_id)

        return PersonaProfile(
            persona_id=persona_id,
            mode="generic",
            style_dimensions=style_dim,
            style_anchor_vector=anchor.style_anchor,
            decision_anchor_vector=anchor.decision_anchor,
            hard_fact_belief_ids=hard_fact_ids,
            language_samples=conversation_samples,
            version=1,
        )

    async def compile_persona(
        self,
        persona_id: str,
        input_text: str,
        core_md: str = "",
        language_samples: list[str] = None,
    ) -> PersonaProfile:
        style_dim = self._style_encoder.encode(input_text)
        anchor = await self._anchor_manager.create_initial_anchor(persona_id, style_dim, input_text)

        hard_fact_ids: list[str] = []
        if core_md.strip():
            hard_fact_ids = await self._hard_fact_guard.extract_from_core_md(core_md, persona_id)

        return PersonaProfile(
            persona_id=persona_id,
            mode="persona",
            style_dimensions=style_dim,
            style_anchor_vector=anchor.style_anchor,
            decision_anchor_vector=anchor.decision_anchor,
            hard_fact_belief_ids=hard_fact_ids,
            language_samples=language_samples or [],
            version=1,
        )


def build_persona_prompt(profile: PersonaProfile) -> str:
    builder = IdentityPromptBuilder(profile)
    return builder.build()
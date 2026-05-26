from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.compiler import PersonaCompiler
from src.persona.profile import PersonaProfile, StyleDimensions


class TestPersonaCompilerCreation:
    def test_compiler_creation(self) -> None:
        anchor_mgr = MagicMock()
        style_encoder = MagicMock()
        hard_fact_guard = MagicMock()
        compiler = PersonaCompiler(anchor_mgr, style_encoder, hard_fact_guard)
        assert compiler._anchor_manager is anchor_mgr
        assert compiler._style_encoder is style_encoder
        assert compiler._hard_fact_guard is hard_fact_guard


class TestCompileGeneric:
    @pytest.mark.asyncio
    async def test_compile_generic_creates_profile(self) -> None:
        style_dim = StyleDimensions(formality=0.7, warmth=0.6)
        style_encoder = MagicMock()
        style_encoder.encode.return_value = style_dim

        class MockAnchorVersion:
            style_anchor = [0.5] * 128
            decision_anchor = [0.3] * 256

        anchor_mgr = AsyncMock()
        anchor_mgr.create_initial_anchor.return_value = MockAnchorVersion()

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = ["fact_1", "fact_2"]

        compiler = PersonaCompiler(anchor_mgr, style_encoder, hard_fact_guard)
        profile = await compiler.compile_generic(
            persona_id="test_generic",
            conversation_samples=["你好", "今天怎么样", "谢谢"],
            core_md="identity|我是助手\n",
        )

        assert isinstance(profile, PersonaProfile)
        assert profile.persona_id == "test_generic"
        assert profile.mode == "generic"
        assert profile.style_dimensions == style_dim
        assert profile.style_anchor_vector == [0.5] * 128
        assert profile.decision_anchor_vector == [0.3] * 256
        assert profile.hard_fact_belief_ids == ["fact_1", "fact_2"]
        assert profile.version == 1
        style_encoder.encode.assert_called_once()
        assert "你好" in profile.language_samples

    @pytest.mark.asyncio
    async def test_compile_generic_without_core_md(self) -> None:
        style_dim = StyleDimensions()
        style_encoder = MagicMock()
        style_encoder.encode.return_value = style_dim

        class MockAnchorVersion:
            style_anchor = [0.5] * 128
            decision_anchor = [0.3] * 256

        anchor_mgr = AsyncMock()
        anchor_mgr.create_initial_anchor.return_value = MockAnchorVersion()

        hard_fact_guard = AsyncMock()

        compiler = PersonaCompiler(anchor_mgr, style_encoder, hard_fact_guard)
        profile = await compiler.compile_generic(
            persona_id="test_no_core",
            conversation_samples=["样本1", "样本2"],
            core_md="",
        )

        assert profile.persona_id == "test_no_core"
        assert profile.hard_fact_belief_ids == []
        hard_fact_guard.extract_from_core_md.assert_not_called()


class TestCompilePersona:
    @pytest.mark.asyncio
    async def test_compile_persona_creates_profile(self) -> None:
        style_dim = StyleDimensions(formality=0.9, warmth=0.8)
        style_encoder = MagicMock()
        style_encoder.encode.return_value = style_dim

        class MockAnchorVersion:
            style_anchor = [0.6] * 128
            decision_anchor = [0.4] * 256

        anchor_mgr = AsyncMock()
        anchor_mgr.create_initial_anchor.return_value = MockAnchorVersion()

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = ["fact_a"]

        compiler = PersonaCompiler(anchor_mgr, style_encoder, hard_fact_guard)
        profile = await compiler.compile_persona(
            persona_id="test_persona",
            input_text="我是一个热情友好的助手，喜欢帮助别人解决问题。",
            core_md="identity|我是助手\nknowledge_boundary|我知道编程知识",
            language_samples=["你好", "有什么可以帮助你的"],
        )

        assert isinstance(profile, PersonaProfile)
        assert profile.persona_id == "test_persona"
        assert profile.mode == "persona"
        assert profile.style_dimensions == style_dim
        assert profile.hard_fact_belief_ids == ["fact_a"]
        assert len(profile.language_samples) == 2

    @pytest.mark.asyncio
    async def test_compile_persona_without_language_samples(self) -> None:
        style_dim = StyleDimensions()
        style_encoder = MagicMock()
        style_encoder.encode.return_value = style_dim

        class MockAnchorVersion:
            style_anchor = [0.5] * 128
            decision_anchor = [0.3] * 256

        anchor_mgr = AsyncMock()
        anchor_mgr.create_initial_anchor.return_value = MockAnchorVersion()

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = []

        compiler = PersonaCompiler(anchor_mgr, style_encoder, hard_fact_guard)
        profile = await compiler.compile_persona(
            persona_id="test_no_samples",
            input_text="我是助手",
            core_md="",
        )

        assert profile.language_samples == []
        assert profile.version == 1
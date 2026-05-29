from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.persona.compiler import PersonaCompiler
from src.persona.profile import PersonaProfile, StyleDimensions


class TestPersonaCompilerCreation:
    def test_compiler_creation(self) -> None:
        style_encoder = MagicMock()
        anchor_version_manager = MagicMock()
        hard_fact_guard = MagicMock()
        compiler = PersonaCompiler(
            style_encoder=style_encoder,
            anchor_version_manager=anchor_version_manager,
            hard_fact_guard=hard_fact_guard,
        )
        assert compiler._style_encoder is style_encoder
        assert compiler._anchor_version_manager is anchor_version_manager
        assert compiler._hard_fact_guard is hard_fact_guard

    def test_compiler_creation_with_defaults(self) -> None:
        compiler = PersonaCompiler()
        assert compiler._style_encoder is not None
        assert compiler._anchor_version_manager is not None
        assert compiler._hard_fact_guard is not None
        assert compiler._style_protection is not None


class TestCompileGeneric:
    @pytest.mark.asyncio
    async def test_compile_generic_creates_profile(self) -> None:
        style_dim = StyleDimensions(colloquial=0.3, formal=0.7, expressive=0.6)
        style_encoder = MagicMock()
        profile_mock = MagicMock()
        profile_mock.overall_score = 0.6
        profile_mock.style_type = "knowledge_sharing"
        profile_mock.confidence = 0.8
        profile_mock.dimensions = {
            "colloquial": MagicMock(value=0.3),
            "formal": MagicMock(value=0.7),
            "emotional": MagicMock(value=0.5),
            "interactive": MagicMock(value=0.4),
            "logical": MagicMock(value=0.6),
            "concise": MagicMock(value=0.5),
            "expressive": MagicMock(value=0.6),
        }
        style_encoder.encode.return_value = profile_mock

        anchor_mgr = AsyncMock()
        anchor_mgr.create_new_version.return_value = MagicMock(
            version_id="v1", version_number=1
        )

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = ["fact_1", "fact_2"]

        text_analyzer = AsyncMock()
        from src.persona.style.base import StyleExtractionResult
        text_analyzer.extract.return_value = StyleExtractionResult(
            sentence_patterns={},
            vocabulary_metrics={"ttr": 0.6, "hapax_ratio": 0.3},
            num_sentences=3,
            num_words=10,
            total_chars=50,
        )

        style_vector_gen = AsyncMock()
        style_vector_gen.generate.return_value = MagicMock(
            vector=[0.1] * 60, consistency_score=0.8
        )

        style_anchor_encoder = AsyncMock()
        style_anchor_encoder.encode_deterministic.return_value = MagicMock(
            vector=[0.5] * 128, checksum="abc123"
        )

        decision_encoder = AsyncMock()
        decision_encoder.encode.return_value = MagicMock(
            vector=[0.3] * 256
        )

        compiler = PersonaCompiler(
            text_analyzer=text_analyzer,
            style_encoder=style_encoder,
            style_vector_gen=style_vector_gen,
            style_anchor_encoder=style_anchor_encoder,
            decision_encoder=decision_encoder,
            anchor_version_manager=anchor_mgr,
            hard_fact_guard=hard_fact_guard,
        )
        profile = await compiler.compile_generic(
            persona_id="test_generic",
            conversation_samples=["你好，今天怎么样？谢谢！这是一段较长的对话样本来满足最小样本量要求。" + "这是一句重复的内容，用于填充字符数以满足最小样本量限制。" * 20],
            core_md="identity|我是助手\n",
        )

        assert isinstance(profile, PersonaProfile)
        assert profile.persona_id == "test_generic"
        assert profile.mode == "generic"
        assert profile.version == 1
        style_encoder.encode.assert_called_once()

    @pytest.mark.asyncio
    async def test_compile_generic_without_core_md(self) -> None:
        style_encoder = MagicMock()
        profile_mock = MagicMock()
        profile_mock.overall_score = 0.5
        profile_mock.style_type = "casual_chat"
        profile_mock.confidence = 0.7
        profile_mock.dimensions = {
            "colloquial": MagicMock(value=0.5),
            "formal": MagicMock(value=0.5),
            "emotional": MagicMock(value=0.5),
            "interactive": MagicMock(value=0.5),
            "logical": MagicMock(value=0.5),
            "concise": MagicMock(value=0.5),
            "expressive": MagicMock(value=0.5),
        }
        style_encoder.encode.return_value = profile_mock

        anchor_mgr = AsyncMock()
        anchor_mgr.create_new_version.return_value = MagicMock(
            version_id="v2", version_number=2
        )

        hard_fact_guard = AsyncMock()

        text_analyzer = AsyncMock()
        from src.persona.style.base import StyleExtractionResult
        text_analyzer.extract.return_value = StyleExtractionResult(
            sentence_patterns={},
            vocabulary_metrics={"ttr": 0.5, "hapax_ratio": 0.2},
            num_sentences=2,
            num_words=8,
            total_chars=40,
        )

        style_vector_gen = AsyncMock()
        style_vector_gen.generate.return_value = MagicMock(
            vector=[0.1] * 60, consistency_score=0.7
        )

        style_anchor_encoder = AsyncMock()
        style_anchor_encoder.encode_deterministic.return_value = MagicMock(
            vector=[0.5] * 128, checksum="def456"
        )

        decision_encoder = AsyncMock()
        decision_encoder.encode.return_value = MagicMock(
            vector=[0.3] * 256
        )

        compiler = PersonaCompiler(
            text_analyzer=text_analyzer,
            style_encoder=style_encoder,
            style_vector_gen=style_vector_gen,
            style_anchor_encoder=style_anchor_encoder,
            decision_encoder=decision_encoder,
            anchor_version_manager=anchor_mgr,
            hard_fact_guard=hard_fact_guard,
        )
        profile = await compiler.compile_generic(
            persona_id="test_no_core",
            conversation_samples=["这是一段较长的对话样本文本，用于满足最小样本量要求。" + "填充字符以满足最小样本量限制。" * 40],
            core_md="",
        )

        assert profile.persona_id == "test_no_core"
        assert profile.hard_fact_belief_ids == []
        hard_fact_guard.extract_from_core_md.assert_not_called()


class TestCompilePersona:
    @pytest.mark.asyncio
    async def test_compile_persona_creates_profile(self) -> None:
        style_encoder = MagicMock()
        profile_mock = MagicMock()
        profile_mock.overall_score = 0.8
        profile_mock.style_type = "knowledge_sharing"
        profile_mock.confidence = 0.9
        profile_mock.dimensions = {
            "colloquial": MagicMock(value=0.3),
            "formal": MagicMock(value=0.9),
            "emotional": MagicMock(value=0.5),
            "interactive": MagicMock(value=0.4),
            "logical": MagicMock(value=0.7),
            "concise": MagicMock(value=0.5),
            "expressive": MagicMock(value=0.6),
        }
        style_encoder.encode.return_value = profile_mock

        anchor_mgr = AsyncMock()
        anchor_mgr.create_new_version.return_value = MagicMock(
            version_id="v3", version_number=3
        )

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = ["fact_a"]

        text_analyzer = AsyncMock()
        from src.persona.style.base import StyleExtractionResult
        text_analyzer.extract.return_value = StyleExtractionResult(
            sentence_patterns={},
            vocabulary_metrics={"ttr": 0.7, "hapax_ratio": 0.4},
            num_sentences=4,
            num_words=15,
            total_chars=60,
        )

        style_vector_gen = AsyncMock()
        style_vector_gen.generate.return_value = MagicMock(
            vector=[0.2] * 60, consistency_score=0.85
        )

        style_anchor_encoder = AsyncMock()
        style_anchor_encoder.encode_deterministic.return_value = MagicMock(
            vector=[0.6] * 128, checksum="ghi789"
        )

        decision_encoder = AsyncMock()
        decision_encoder.encode.return_value = MagicMock(
            vector=[0.4] * 256
        )

        semantic_translator = AsyncMock()
        semantic_translator.translate.return_value = {"authentic": 0.9, "helpful": 0.8}

        compiler = PersonaCompiler(
            text_analyzer=text_analyzer,
            style_encoder=style_encoder,
            style_vector_gen=style_vector_gen,
            style_anchor_encoder=style_anchor_encoder,
            decision_encoder=decision_encoder,
            anchor_version_manager=anchor_mgr,
            hard_fact_guard=hard_fact_guard,
            semantic_translator=semantic_translator,
        )
        profile = await compiler.compile_persona(
            persona_id="test_persona",
            input_text="我是一个热情友好的助手，喜欢帮助别人解决问题。" + "这是一句填充文本，用来增加字符数以满足最小样本量的要求。" * 20,
            core_md="identity|我是助手\nknowledge_boundary|我知道编程知识",
            language_samples=["你好", "有什么可以帮助你的"],
        )

        assert isinstance(profile, PersonaProfile)
        assert profile.persona_id == "test_persona"
        assert profile.mode == "persona"
        assert profile.hard_fact_belief_ids == ["fact_a"]
        assert len(profile.language_samples) == 2
        assert profile.values_profile == {"authentic": 0.9, "helpful": 0.8}

    @pytest.mark.asyncio
    async def test_compile_persona_without_language_samples(self) -> None:
        style_encoder = MagicMock()
        profile_mock = MagicMock()
        profile_mock.overall_score = 0.5
        profile_mock.style_type = "casual_chat"
        profile_mock.confidence = 0.6
        profile_mock.dimensions = {
            "colloquial": MagicMock(value=0.5),
            "formal": MagicMock(value=0.5),
            "emotional": MagicMock(value=0.5),
            "interactive": MagicMock(value=0.5),
            "logical": MagicMock(value=0.5),
            "concise": MagicMock(value=0.5),
            "expressive": MagicMock(value=0.5),
        }
        style_encoder.encode.return_value = profile_mock

        anchor_mgr = AsyncMock()
        anchor_mgr.create_new_version.return_value = MagicMock(
            version_id="v4", version_number=4
        )

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = []

        text_analyzer = AsyncMock()
        from src.persona.style.base import StyleExtractionResult
        text_analyzer.extract.return_value = StyleExtractionResult(
            sentence_patterns={},
            vocabulary_metrics={"ttr": 0.4, "hapax_ratio": 0.2},
            num_sentences=2,
            num_words=7,
            total_chars=35,
        )

        style_vector_gen = AsyncMock()
        style_vector_gen.generate.return_value = MagicMock(
            vector=[0.1] * 60, consistency_score=0.6
        )

        style_anchor_encoder = AsyncMock()
        style_anchor_encoder.encode_deterministic.return_value = MagicMock(
            vector=[0.5] * 128, checksum="jkl012"
        )

        decision_encoder = AsyncMock()
        decision_encoder.encode.return_value = MagicMock(
            vector=[0.3] * 256
        )

        config = MagicMock()
        config.min_language_samples = 500
        config.max_language_samples = 10000
        config.enable_anchor_versioning = True
        config.enable_hard_fact_extraction = True
        config.enable_value_translation = False

        compiler = PersonaCompiler(
            text_analyzer=text_analyzer,
            style_encoder=style_encoder,
            style_vector_gen=style_vector_gen,
            style_anchor_encoder=style_anchor_encoder,
            decision_encoder=decision_encoder,
            anchor_version_manager=anchor_mgr,
            hard_fact_guard=hard_fact_guard,
            config=config,
        )
        profile = await compiler.compile_persona(
            persona_id="test_no_samples",
            input_text="我是助手，这是一个较长的输入文本来满足最小样本量的要求。" + "这是一句填充文本，用来增加字符数以满足最小样本量的要求。" * 20,
            core_md="",
        )

        assert profile.version == 1


class TestCompilePersonaWithoutTranslator:
    @pytest.mark.asyncio
    async def test_compile_persona_disabled_value_translation(self) -> None:
        style_encoder = MagicMock()
        profile_mock = MagicMock()
        profile_mock.overall_score = 0.5
        profile_mock.style_type = "casual_chat"
        profile_mock.confidence = 0.6
        profile_mock.dimensions = {
            "colloquial": MagicMock(value=0.5),
            "formal": MagicMock(value=0.5),
            "emotional": MagicMock(value=0.5),
            "interactive": MagicMock(value=0.5),
            "logical": MagicMock(value=0.5),
            "concise": MagicMock(value=0.5),
            "expressive": MagicMock(value=0.5),
        }
        style_encoder.encode.return_value = profile_mock

        anchor_mgr = AsyncMock()
        anchor_mgr.create_new_version.return_value = MagicMock(
            version_id="v5", version_number=5
        )

        hard_fact_guard = AsyncMock()
        hard_fact_guard.extract_from_core_md.return_value = []

        text_analyzer = AsyncMock()
        from src.persona.style.base import StyleExtractionResult
        text_analyzer.extract.return_value = StyleExtractionResult(
            sentence_patterns={},
            vocabulary_metrics={"ttr": 0.4, "hapax_ratio": 0.2},
            num_sentences=2,
            num_words=7,
            total_chars=35,
        )

        style_vector_gen = AsyncMock()
        style_vector_gen.generate.return_value = MagicMock(
            vector=[0.1] * 60, consistency_score=0.6
        )

        style_anchor_encoder = AsyncMock()
        style_anchor_encoder.encode_deterministic.return_value = MagicMock(
            vector=[0.5] * 128, checksum="jkl012"
        )

        decision_encoder = AsyncMock()
        decision_encoder.encode.return_value = MagicMock(
            vector=[0.3] * 256
        )

        config = MagicMock()
        config.min_language_samples = 500
        config.max_language_samples = 10000
        config.enable_anchor_versioning = True
        config.enable_hard_fact_extraction = True
        config.enable_value_translation = False

        compiler = PersonaCompiler(
            text_analyzer=text_analyzer,
            style_encoder=style_encoder,
            style_vector_gen=style_vector_gen,
            style_anchor_encoder=style_anchor_encoder,
            decision_encoder=decision_encoder,
            anchor_version_manager=anchor_mgr,
            hard_fact_guard=hard_fact_guard,
            config=config,
        )
        profile = await compiler.compile_persona(
            persona_id="test_disabled",
            input_text="我是助手，这是一个较长的输入文本来满足最小样本量的要求。" + "这是一句填充文本，用来增加字符数以满足最小样本量的要求。" * 20,
            core_md="",
        )

        assert profile.version == 1
        assert profile.values_profile is None
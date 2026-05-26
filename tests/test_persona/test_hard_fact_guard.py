from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.interfaces import Belief
from src.persona.hard_fact_guard import CATEGORIES, EXTRACTION_PROMPT, HardFactGuard


class MockBelief(Belief):
    def __init__(self, belief_id: str, content: str, confidence: float = 0.99, metadata: dict = None):
        super().__init__(
            id=belief_id,
            content=content,
            source="system",
            confidence=confidence,
            base_confidence=confidence,
            metadata=metadata or {},
        )


def _make_mock_belief_store() -> AsyncMock:
    store = AsyncMock()
    store.search_similar.return_value = []
    store.add.return_value = str(uuid4())
    store.get.return_value = None
    return store


def _mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_hard_fact = MagicMock()
    mock_hard_fact.categories = ["identity", "knowledge_boundary", "relation", "bottom_line"]
    mock_hard_fact.confidence = 0.99
    mock_hard_fact.memory_type = "identity"
    mock_hard_fact.layer = 1

    mock_persona = MagicMock()
    mock_persona.hard_fact = mock_hard_fact

    mock_settings = MagicMock()
    mock_settings.persona = mock_persona

    monkeypatch.setattr("src.config.get_settings", lambda: mock_settings)


class TestExtractFromCoreMd:
    @pytest.mark.asyncio
    async def test_parse_category_content_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)

        core_md = (
            "identity|我是ShuyuanCore，一个AI助手\n"
            "knowledge_boundary|我了解编程、数学和自然科学\n"
            "relation|我与用户是协作关系\n"
            "bottom_line|我不能伤害人类\n"
        )
        belief_ids = await guard.extract_from_core_md(core_md, "test_persona")

        assert len(belief_ids) == 4
        assert store.add.call_count == 4

        calls = store.add.call_args_list
        for call in calls:
            _, kwargs = call
            assert kwargs["conversation_id"] == "persona_global"
            belief = kwargs["belief"]
            assert belief.source == "system"
            assert belief.confidence == 0.99

    @pytest.mark.asyncio
    async def test_empty_core_md_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        belief_ids = await guard.extract_from_core_md("", "test_persona")
        assert belief_ids == []

    @pytest.mark.asyncio
    async def test_skip_invalid_format_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)

        core_md = (
            "identity|我是助手\n"
            "invalid line without pipe\n"
            "random text\n"
            "bottom_line|不能伤害\n"
        )
        belief_ids = await guard.extract_from_core_md(core_md, "test_persona")
        assert len(belief_ids) == 2

    @pytest.mark.asyncio
    async def test_skip_empty_content_after_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        core_md = "identity|\nbottom_line|不能伤害\n"
        belief_ids = await guard.extract_from_core_md(core_md, "test_persona")
        assert len(belief_ids) == 1


class TestDuplicateDetection:
    @pytest.mark.asyncio
    async def test_duplicate_content_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        existing_id = str(uuid4())
        store = AsyncMock()
        store.search_similar.return_value = [
            (MockBelief(existing_id, "我是助手", confidence=0.99), 0.95),
        ]
        store.add.return_value = str(uuid4())

        guard = HardFactGuard(belief_store=store)
        core_md = "identity|我是助手\n"
        belief_ids = await guard.extract_from_core_md(core_md, "test_persona")

        assert belief_ids == [existing_id]
        store.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_with_belief_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_settings(monkeypatch)

        existing_id = str(uuid4())
        store = AsyncMock()
        store.search_similar.return_value = [
            MockBelief(existing_id, "我是助手", confidence=0.99),
        ]
        store.add.return_value = str(uuid4())

        guard = HardFactGuard(belief_store=store)
        core_md = "identity|我是助手\n"
        belief_ids = await guard.extract_from_core_md(core_md, "test_persona")

        assert belief_ids == [existing_id]


class TestBuildGuardPrompt:
    def test_empty_belief_ids_returns_empty(self) -> None:
        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        prompt = guard.build_guard_prompt([])
        assert prompt == ""

    def test_build_guard_prompt_sync_fallback(self) -> None:
        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        prompt = guard._build_guard_prompt_sync(["fact_1", "fact_2"])
        assert "硬事实" in prompt
        assert "fact_1" in prompt
        assert "fact_2" in prompt

    def test_format_facts_with_data(self) -> None:
        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        facts = [("identity", "我是助手"), ("bottom_line", "不能伤害")]
        prompt = guard._format_facts(facts)
        assert "以下硬事实不可违背" in prompt
        assert "[identity]" in prompt
        assert "我是助手" in prompt
        assert "[bottom_line]" in prompt
        assert "不能伤害" in prompt

    def test_format_facts_empty(self) -> None:
        store = _make_mock_belief_store()
        guard = HardFactGuard(belief_store=store)
        assert guard._format_facts([]) == ""

    def test_extraction_prompt_contains_categories(self) -> None:
        assert "CATEGORY|内容" in EXTRACTION_PROMPT
        for cat in CATEGORIES:
            assert cat in EXTRACTION_PROMPT
        assert "{core_md}" in EXTRACTION_PROMPT
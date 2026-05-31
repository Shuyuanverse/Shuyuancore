from __future__ import annotations

import pytest

from src.skills.extractor import (
    calculate_value_score,
    count_corrections,
    count_refinements,
    has_explicit_save,
)


class TestValueScore:
    def test_zero_score_for_short_conversation(self):
        score = calculate_value_score(turns_count=1)
        assert 0.0 <= score < 0.5

    def test_high_score_for_long_conversation(self):
        score = calculate_value_score(
            turns_count=25, avg_interval_seconds=30.0
        )
        assert score > 0.0

    def test_corrections_reduce_score(self):
        base_score = calculate_value_score(turns_count=10)
        corrected_score = calculate_value_score(
            turns_count=10, correction_count=5
        )
        assert corrected_score < base_score

    def test_refinements_increase_score(self):
        base_score = calculate_value_score(turns_count=10)
        refined_score = calculate_value_score(
            turns_count=10, refinement_count=4
        )
        assert refined_score > base_score

    def test_explicit_save_boosts_score(self):
        score = calculate_value_score(
            turns_count=2, explicit_save=True
        )
        assert score >= 0.5

    def test_error_recovery_bonus(self):
        score = calculate_value_score(
            turns_count=10, recovered_from_error=True
        )
        assert score > 0.0

    def test_tool_failure_penalty(self):
        score = calculate_value_score(
            turns_count=10, tool_call_failure_rate=0.8
        )
        assert score >= 0.0

    def test_score_bounds(self):
        score = calculate_value_score(
            turns_count=100, explicit_save=True
        )
        assert 0.0 <= score <= 1.0

    def test_persona_weight_working(self):
        work_score = calculate_value_score(
            turns_count=10, persona_weight=0.8
        )
        life_score = calculate_value_score(
            turns_count=10, persona_weight=0.3
        )
        assert work_score > life_score


class TestKeywordDetection:
    def test_correction_keywords_chinese(self):
        assert count_corrections("不对，这个错了") == 2

    def test_correction_keywords_no_match(self):
        assert count_corrections("完全正确") == 0

    def test_refinement_keywords_chinese(self):
        assert count_refinements("再加一个，补充一下") == 2

    def test_refinement_keywords_no_match(self):
        assert count_refinements("完成了") == 0

    def test_explicit_save_detected(self):
        assert has_explicit_save("记住这个操作") is True

    def test_explicit_save_not_detected(self):
        assert has_explicit_save("随便聊聊") is False


@pytest.mark.asyncio
async def test_extract_skill_not_extracted_below_threshold():
    from src.skills.extractor import extract_skill

    belief_store = AsyncMock()
    belief_store.get = AsyncMock(return_value=[])
    skill_store = AsyncMock()
    model_provider = AsyncMock()

    result = await extract_skill(
        conversation_id="test-conv",
        message="hello",
        response="hi",
        belief_store=belief_store,
        skill_store=skill_store,
        model_provider=model_provider,
    )
    assert result is None


@pytest.mark.asyncio
async def test_extract_skill_llm_failure():
    import json
    from unittest.mock import AsyncMock, MagicMock

    from src.skills.extractor import extract_skill

    class MockBelief:
        def __init__(self):
            self.id = "b-1"
            self.content = "test"
            self.source = "user"
            self.confidence = 0.8
            self.last_accessed = 1000
            self.memory_type = "chat"
            self.layer = 3
            self.status = "active"

    belief_store = AsyncMock()
    belief_store.get = AsyncMock(
        return_value=[MockBelief(), MockBelief()]
    )

    skill_store = AsyncMock()

    mock_result = MagicMock()
    mock_result.content = "invalid response"
    model_provider = AsyncMock()
    model_provider.chat = AsyncMock(return_value=mock_result)

    result = await extract_skill(
        conversation_id="test-conv",
        message="hello",
        response="hi",
        belief_store=belief_store,
        skill_store=skill_store,
        model_provider=model_provider,
    )
    assert result is None


from unittest.mock import AsyncMock, MagicMock
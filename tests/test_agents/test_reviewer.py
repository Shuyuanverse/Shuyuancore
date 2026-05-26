from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.interfaces import UpdateContext, UpdaterResult
from src.agents.reviewer import Reviewer, _parse_review_json, _default_review_pass
from src.models.interfaces import ChatResult, IModelProvider


def _make_ctx(message: str = "hello") -> UpdateContext:
    return UpdateContext(
        conversation_id="conv1",
        user_id="user1",
        message=message,
    )


def _make_provider(response_content: str) -> IModelProvider:
    provider = MagicMock(spec=IModelProvider)
    provider.chat = AsyncMock(
        return_value=ChatResult(content=response_content, model_used="test")
    )
    return provider


class TestParseReviewJson:

    def test_valid_pass(self) -> None:
        raw = '{"pass": true, "issues": [], "suggestions": []}'
        result = _parse_review_json(raw)
        assert result["pass"] is True
        assert result["issues"] == []

    def test_valid_fail(self) -> None:
        raw = (
            '{"pass": false, '
            '"issues": [{"dimension": "completeness", "description": "缺失关键信息"}], '
            '"suggestions": ["补充方案对比"]}'
        )
        result = _parse_review_json(raw)
        assert result["pass"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["dimension"] == "completeness"

    def test_invalid_json_defaults_to_pass(self) -> None:
        raw = "some text without json"
        result = _parse_review_json(raw)
        assert result["pass"] is True

    def test_default_review_pass(self) -> None:
        result = _default_review_pass()
        assert result["pass"] is True
        assert result["issues"] == []
        assert result["suggestions"] == []


class TestReviewer:

    @pytest.mark.asyncio
    async def test_review_pass(self) -> None:
        provider = _make_provider(
            '{"pass": true, "issues": [], "suggestions": []}'
        )
        reviewer = Reviewer(provider)
        ctx = _make_ctx("我应该怎么学 Python？")
        result = await reviewer.review(ctx, "建议从官方文档开始学习。")
        assert result["pass"] is True

    @pytest.mark.asyncio
    async def test_review_with_issues(self) -> None:
        provider = _make_provider(
            '{"pass": false, '
            '"issues": [{"dimension": "consistency", "description": "前后矛盾"}], '
            '"suggestions": ["统一术语"]}'
        )
        reviewer = Reviewer(provider)
        ctx = _make_ctx("对比A和B")
        draft = "A很好。B也很好。选A吧。但是B更好。"
        result = await reviewer.review(ctx, draft)
        assert result["pass"] is False
        assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_llm_failure_returns_pass(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        provider.chat = AsyncMock(side_effect=RuntimeError("api down"))
        reviewer = Reviewer(provider)
        ctx = _make_ctx("hello")
        result = await reviewer.review(ctx, "some draft")
        assert result["pass"] is True

    @pytest.mark.asyncio
    async def test_empty_draft(self) -> None:
        provider = _make_provider(
            '{"pass": false, '
            '"issues": [{"dimension": "completeness", "description": "内容为空"}], '
            '"suggestions": ["提供实质性内容"]}'
        )
        reviewer = Reviewer(provider)
        ctx = _make_ctx("hello")
        result = await reviewer.review(ctx, "")
        assert isinstance(result, dict)
        assert "pass" in result

    @pytest.mark.asyncio
    async def test_check_against_beliefs_no_store(self) -> None:
        provider = MagicMock(spec=IModelProvider)
        reviewer = Reviewer(provider)
        ctx = _make_ctx("hello")
        issues = await reviewer._check_against_beliefs(ctx, "draft")
        assert issues == []
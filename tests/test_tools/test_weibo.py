from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.weibo import WeiBoTool


class TestWeiBoTool:

    def test_weibo_get_spec(self) -> None:
        tool = WeiBoTool()
        spec = tool.get_spec()
        assert spec.name == "weibo"
        assert spec.category == "social"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_weibo_validate_invalid_action(self) -> None:
        tool = WeiBoTool()
        errors = await tool.validate({"action": "fly"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "fly" in errors[0]

    @pytest.mark.asyncio
    async def test_weibo_validate_no_keyword(self) -> None:
        tool = WeiBoTool()
        errors = await tool.validate({"action": "search_weibo"})
        assert len(errors) >= 1
        assert any("'keyword' is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_weibo_validate_valid(self) -> None:
        tool = WeiBoTool()
        errors = await tool.validate({
            "action": "search_weibo",
            "keyword": "AI",
        })
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_weibo_execute_search_weibo(self) -> None:
        mock_html = (
            '<div class="card-wrap">'
            '<p class="txt">Test weibo content weibo_id=123456</p>'
            '<a href="//weibo.com/123456/abc">link</a>'
            '</div>'
            '<div class="card-wrap">'
            '<p class="txt">Second post content weibo_id=789012</p>'
            '<a href="//weibo.com/789012/def">link</a>'
            '</div>'
        )

        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        tool = WeiBoTool()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({
                "action": "search_weibo",
                "keyword": "test",
                "limit": 10,
                "timeout": 30,
            })

        assert result.success
        assert result.data is not None
        assert result.data["keyword"] == "test"
        assert len(result.data["posts"]) == 2
        assert result.data["posts"][0]["id"] == "123456"
        assert "Test weibo content" in result.data["posts"][0]["text"]
        assert result.data["posts"][1]["id"] == "789012"
        assert "Second post" in result.data["posts"][1]["text"]
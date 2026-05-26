from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.wechat_mp import WeChatMpTool


class TestWeChatMpTool:

    def test_wechat_get_spec(self) -> None:
        tool = WeChatMpTool()
        spec = tool.get_spec()
        assert spec.name == "wechat_mp"
        assert spec.category == "social"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_wechat_validate_invalid_action(self) -> None:
        tool = WeChatMpTool()
        errors = await tool.validate({"action": "fly"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "fly" in errors[0]

    @pytest.mark.asyncio
    async def test_wechat_validate_no_keyword(self) -> None:
        tool = WeChatMpTool()
        errors = await tool.validate({"action": "search_article"})
        assert len(errors) >= 1
        assert any("'keyword' is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_wechat_validate_valid(self) -> None:
        tool = WeChatMpTool()
        errors = await tool.validate({
            "action": "search_article",
            "keyword": "AI",
        })
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_wechat_execute_search_article(self) -> None:
        mock_html = (
            '<div class="wx-rb">'
            '<a class="account">TestAccount</a>'
            '<p class="txt-info">Summary of article 1</p>'
            '<h3><a>Article Title 1</a></h3>'
            '<a href="//mp.weixin.qq.com/s/article1" target="_blank">read</a>'
            '</div>'
            '<div class="wx-rb">'
            '<a class="account">TestAccount2</a>'
            '<p class="txt-info">Summary of article 2</p>'
            '<h3><a>Article Title 2</a></h3>'
            '<a href="//mp.weixin.qq.com/s/article2" target="_blank">read</a>'
            '</div>'
        )

        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        tool = WeChatMpTool()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({
                "action": "search_article",
                "keyword": "AI",
                "limit": 10,
                "timeout": 30,
            })

        assert result.success
        assert result.data is not None
        assert result.data["keyword"] == "AI"
        assert len(result.data["articles"]) == 2
        assert result.data["articles"][0]["title"] == "Article Title 1"
        assert result.data["articles"][0]["account"] == "TestAccount"
        assert "Summary of article 1" in result.data["articles"][0]["summary"]
        assert "https://mp.weixin.qq.com/s/article1" in result.data["articles"][0]["url"]
        assert result.data["articles"][1]["title"] == "Article Title 2"
        assert result.data["articles"][1]["account"] == "TestAccount2"
        assert "Summary of article 2" in result.data["articles"][1]["summary"]
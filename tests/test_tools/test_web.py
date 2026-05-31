from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tools.builtin.web import WebTool


class TestWebTool:

    def test_web_get_spec(self) -> None:
        tool = WebTool()
        spec = tool.get_spec()
        assert spec.name == "web"
        assert spec.category == "web"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_web_validate_invalid_action(self) -> None:
        tool = WebTool()
        errors = await tool.validate({"action": "post"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "post" in errors[0]

    @pytest.mark.asyncio
    async def test_web_validate_no_params(self) -> None:
        tool = WebTool()
        errors_get = await tool.validate({"action": "get"})
        assert any("url" in e for e in errors_get)

        errors_search = await tool.validate({"action": "search"})
        assert any("query" in e for e in errors_search)

    @pytest.mark.asyncio
    async def test_web_validate_valid(self) -> None:
        tool = WebTool()
        errors_get = await tool.validate({
            "action": "get",
            "url": "https://example.com",
        })
        assert errors_get == []

        errors_search = await tool.validate({
            "action": "search",
            "query": "hello world",
        })
        assert errors_search == []

    @pytest.mark.asyncio
    async def test_web_execute_get_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Hello, ShuyuanCore!"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.url = httpx.URL("https://example.com")

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        tool = WebTool()
        with patch(
            "src.tools.builtin.web.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute({
                "action": "get",
                "url": "https://example.com",
                "respect_robots": False,
            })

        assert result.success
        assert result.data["content"] == "Hello, ShuyuanCore!"
        assert result.data["status_code"] == 200

    @pytest.mark.asyncio
    async def test_web_execute_get_http_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=mock_resp,
        )

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        tool = WebTool()
        with patch(
            "src.tools.builtin.web.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute({
                "action": "get",
                "url": "https://example.com/notfound",
                "respect_robots": False,
            })

        assert not result.success
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_web_execute_search_success(self) -> None:
        mock_html = (
            '<div class="result">'
            '<a class="result__a" href="https://example.com">Example Title</a>'
            '<a class="result__snippet">Example snippet text</a>'
            "</div>"
            '<div class="result">'
            '<a class="result__a" href="https://example.org">Second Result</a>'
            '<a class="result__snippet">Second snippet text</a>'
            "</div>"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_response.url = httpx.URL("https://html.duckduckgo.com/html/")

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        tool = WebTool()
        with patch(
            "src.tools.builtin.web.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute({
                "action": "search",
                "query": "shuyuan core",
                "max_results": 5,
            })

        assert result.success
        assert len(result.data["results"]) == 2
        assert result.data["results"][0]["title"] == "Example Title"
        assert result.data["results"][1]["url"] == "https://example.org"

    @pytest.mark.asyncio
    async def test_web_execute_robots_blocked(self) -> None:
        mock_robots_resp = MagicMock()
        mock_robots_resp.status_code = 200
        mock_robots_resp.text = "User-agent: *\nDisallow: /"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_robots_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_rp = MagicMock()
        mock_rp.can_fetch.return_value = False

        tool = WebTool()
        with patch(
            "src.tools.builtin.web.httpx.AsyncClient",
            return_value=mock_client,
        ), patch(
            "src.tools.builtin.web.RobotFileParser",
            return_value=mock_rp,
        ):
            result = await tool.execute({
                "action": "get",
                "url": "https://example.com/blocked",
                "respect_robots": True,
            })

        assert not result.success
        assert "robots.txt" in result.error
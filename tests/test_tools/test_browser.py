from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.browser import BrowserTool
from src.tools.interfaces import ToolResult


class TestBrowserTool:

    def test_browser_get_spec(self) -> None:
        tool = BrowserTool()
        spec = tool.get_spec()
        assert spec.name == "browser"
        assert spec.category == "web"
        assert spec.dangerous is True

    @pytest.mark.asyncio
    async def test_browser_validate_invalid_action(self) -> None:
        tool = BrowserTool()
        errors = await tool.validate({"action": "fly"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "fly" in errors[0]

    @pytest.mark.asyncio
    async def test_browser_validate_missing_params(self) -> None:
        tool = BrowserTool()
        errors_nav = await tool.validate({"action": "navigate"})
        assert any("url" in e and "required" in e for e in errors_nav)

        errors_click = await tool.validate({"action": "click"})
        assert any("selector" in e and "required" in e for e in errors_click)

        errors_fill = await tool.validate({"action": "fill"})
        assert any("selector" in e and "required" in e for e in errors_fill)

    @pytest.mark.asyncio
    async def test_browser_validate_valid(self) -> None:
        tool = BrowserTool()
        errors = await tool.validate({
            "action": "navigate",
            "url": "https://example.com",
        })
        assert len(errors) == 0

        errors_click = await tool.validate({
            "action": "click",
            "selector": "#btn",
        })
        assert len(errors_click) == 0

        errors_fill = await tool.validate({
            "action": "fill",
            "selector": "#input",
            "value": "hello",
        })
        assert len(errors_fill) == 0

    @pytest.mark.asyncio
    async def test_browser_execute_playwright_not_installed(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "apr_playwright"
        tool = BrowserTool()
        with (
            patch(
                "src.tools.builtin.browser.request_approval",
                AsyncMock(return_value=mock_req),
            ),
            patch(
                "src.tools.builtin.browser.wait_for_approval",
                AsyncMock(return_value=True),
            ),
            patch.object(
                BrowserTool, "_check_playwright", return_value=False,
            ),
        ):
            result = await tool.execute({
                "action": "navigate",
                "url": "https://example.com",
            })
            assert not result.success
            assert "Playwright is not installed" in result.error

    @pytest.mark.asyncio
    async def test_browser_execute_navigate(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "apr_nav"
        mock_result = ToolResult(
            success=True,
            data={
                "title": "Example Title",
                "url": "https://example.com",
                "status": "loaded",
            },
        )
        tool = BrowserTool()
        with (
            patch(
                "src.tools.builtin.browser.request_approval",
                AsyncMock(return_value=mock_req),
            ),
            patch(
                "src.tools.builtin.browser.wait_for_approval",
                AsyncMock(return_value=True),
            ),
            patch.object(
                BrowserTool, "_check_playwright", return_value=True,
            ),
            patch.object(
                BrowserTool, "_perform_action",
                AsyncMock(return_value=mock_result),
            ),
        ):
            result = await tool.execute({
                "action": "navigate",
                "url": "https://example.com",
            })
            assert result.success
            assert result.data["title"] == "Example Title"
            assert result.data["url"] == "https://example.com"
            assert result.data["status"] == "loaded"

    @pytest.mark.asyncio
    async def test_browser_execute_approval_denied(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "apr_denied"
        tool = BrowserTool()
        with (
            patch(
                "src.tools.builtin.browser.request_approval",
                AsyncMock(return_value=mock_req),
            ),
            patch(
                "src.tools.builtin.browser.wait_for_approval",
                AsyncMock(return_value=False),
            ),
        ):
            result = await tool.execute({
                "action": "navigate",
                "url": "https://example.com",
            })
            assert not result.success
            assert "not approved" in result.error
            assert result.approval_id == "apr_denied"
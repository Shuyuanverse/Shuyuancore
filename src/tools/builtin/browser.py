from __future__ import annotations

import time
from typing import Any

from src.tools.approval import request_approval, wait_for_approval
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "screenshot",
        "navigate",
        "click",
        "fill",
        "text_content",
    }
)

ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "screenshot": {"url"},
    "navigate": {"url"},
    "click": {"selector"},
    "fill": {"selector", "value"},
    "text_content": {"selector"},
}


class BrowserTool(ITool):
    """Browser automation tool using Playwright.

    Supports navigating to URLs, taking screenshots, clicking elements,
    filling form fields, and extracting text content from web pages.
    All operations are considered dangerous and require approval.
    """

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="browser",
            description=(
                "Browser automation: navigate, screenshot, click, "
                "fill form fields, and extract text content"
            ),
            category="web",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=("Action to perform: screenshot/navigate/click/fill/text_content"),
                    required=True,
                ),
                ToolParameter(
                    name="url",
                    type="string",
                    description=("Target URL, required for navigate and screenshot"),
                    required=False,
                ),
                ToolParameter(
                    name="selector",
                    type="string",
                    description=("CSS selector, required for click, fill, and text_content"),
                    required=False,
                ),
                ToolParameter(
                    name="value",
                    type="string",
                    description="Value to fill, required for fill action",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Timeout in milliseconds",
                    required=False,
                    default=30000,
                ),
            ],
        )

    @classmethod
    def _check_playwright(cls) -> bool:
        """Check if the playwright package is available.

        Returns:
            True if playwright can be imported, False otherwise.
        """

        try:
            import playwright  # noqa: F401

            return True
        except ImportError:
            return False

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec describing the browser tool.
        """

        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """

        errors: list[str] = []
        action: str = params.get("action", "").strip()

        if not action:
            errors.append("action is required and must not be empty")
            return errors

        if action not in VALID_ACTIONS:
            valid = ", ".join(sorted(VALID_ACTIONS))
            errors.append(f"Invalid action: {action}. Must be one of: {valid}")
            return errors

        required = ACTION_REQUIRED_PARAMS.get(action, set())
        for param in required:
            value = params.get(param)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"'{param}' is required for action '{action}'")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the requested browser action.

        All operations require approval. Launches a headless browser,
        performs the action, and closes the browser.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with operation outcome.
        """

        start = time.time()
        action: str = params.get("action", "")

        approval_req = await request_approval(
            tool_name="browser",
            params=params,
            user_id=user_id,
        )
        approved = await wait_for_approval(approval_req.approval_id)
        if not approved:
            return ToolResult(
                success=False,
                error=f"Browser action '{action}' was not approved",
                approval_id=approval_req.approval_id,
                duration_ms=(time.time() - start) * 1000,
            )

        if not self._check_playwright():
            return ToolResult(
                success=False,
                error=(
                    "Playwright is not installed. "
                    "Install it with: pip install playwright && "
                    "playwright install chromium"
                ),
                approval_id=approval_req.approval_id,
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            result = await self._perform_action(params)
            result.approval_id = approval_req.approval_id
            result.duration_ms = (time.time() - start) * 1000
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                approval_id=approval_req.approval_id,
                duration_ms=(time.time() - start) * 1000,
            )

    async def _perform_action(self, params: dict[str, Any]) -> ToolResult:
        """Perform the requested browser action using Playwright.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with action result.
        """

        from playwright.async_api import async_playwright

        action: str = params["action"]
        timeout: int = params.get("timeout", 30000)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                if action == "navigate":
                    url: str = params["url"]
                    await page.goto(url, timeout=timeout)
                    title = await page.title()
                    return ToolResult(
                        success=True,
                        data={
                            "title": title,
                            "url": page.url,
                            "status": "loaded",
                        },
                    )

                elif action == "screenshot":
                    target_url: str = params["url"]
                    await page.goto(target_url, timeout=timeout)
                    await page.wait_for_load_state("networkidle")
                    screenshot_bytes = await page.screenshot(full_page=True, type="png")
                    import base64

                    encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
                    return ToolResult(
                        success=True,
                        data={
                            "screenshot": encoded,
                            "url": page.url,
                            "format": "base64_png",
                        },
                    )

                elif action == "click":
                    selector: str = params["selector"]
                    await page.click(selector, timeout=timeout)
                    return ToolResult(
                        success=True,
                        data={
                            "action": "click",
                            "selector": selector,
                            "status": "clicked",
                        },
                    )

                elif action == "fill":
                    fill_selector: str = params["selector"]
                    value: str = params["value"]
                    await page.fill(fill_selector, value, timeout=timeout)
                    return ToolResult(
                        success=True,
                        data={
                            "action": "fill",
                            "selector": fill_selector,
                            "status": "filled",
                        },
                    )

                elif action == "text_content":
                    element_selector: str = params["selector"]
                    element = await page.wait_for_selector(element_selector, timeout=timeout)
                    if element is None:
                        return ToolResult(
                            success=False,
                            error=f"Element not found: {selector}",
                        )
                    text = await element.text_content()
                    return ToolResult(
                        success=True,
                        data={
                            "selector": element_selector,
                            "text": (text or "").strip(),
                        },
                    )

                else:
                    return ToolResult(
                        success=False,
                        error=f"Unknown action: {action}",
                    )

            finally:
                await browser.close()

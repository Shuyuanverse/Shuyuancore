from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class ApiDebugTool(ITool):
    """API 调试工具 — 用于测试和调试 HTTP API 接口。

    Supports GET and POST requests with custom headers and
    response preview. Useful for developers to inspect API
    endpoints during development and debugging.
    """

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="api_debug",
            description=(
                "API debug tool for testing HTTP API endpoints. "
                "Supports GET and POST requests with custom headers "
                "and response preview. Use with caution in production."
            ),
            category="extension",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="method",
                    type="string",
                    description="HTTP method: 'GET' or 'POST'",
                    required=True,
                ),
                ToolParameter(
                    name="url",
                    type="string",
                    description="Target API endpoint URL",
                    required=True,
                ),
                ToolParameter(
                    name="headers",
                    type="object",
                    description=(
                        "Optional custom headers as a JSON object "
                        '(e.g., {"Authorization": "Bearer xxx"})'
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="body",
                    type="object",
                    description=(
                        "Optional JSON body for POST requests. "
                        "Provide as a JSON object."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec describing this tool's metadata and parameters.
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

        method = params.get("method", "")
        if method not in ("GET", "POST"):
            errors.append("'method' must be either 'GET' or 'POST'")

        url = params.get("url", "")
        if not url or not isinstance(url, str) or not url.strip():
            errors.append("'url' is required and must be a non-empty string")

        headers = params.get("headers")
        if headers is not None and not isinstance(headers, dict):
            errors.append("'headers' must be a JSON object (dict) if provided")

        body = params.get("body")
        if body is not None and not isinstance(body, dict):
            errors.append("'body' must be a JSON object (dict) if provided")

        timeout = params.get("timeout", 30)
        if timeout is not None:
            try:
                tv = int(timeout)
                if tv < 1 or tv > 120:
                    errors.append("'timeout' must be between 1 and 120")
            except (TypeError, ValueError):
                errors.append("'timeout' must be an integer")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute an HTTP API debug request.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with the API response or error information.
        """
        method = params.get("method", "GET").upper()
        url = params.get("url", "").strip()
        headers = params.get("headers") or {}
        body = params.get("body")
        timeout = int(params.get("timeout", 30))

        start_time = time.time()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(
                        url,
                        headers=headers,
                        json=body,
                    )

                duration_ms = (time.time() - start_time) * 1000

                response_body: str | dict[str, Any]
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        response_body = response.json()
                    except (json.JSONDecodeError, ValueError):
                        response_body = response.text
                else:
                    response_body = response.text

                preview = response_body
                if isinstance(preview, str) and len(preview) > 2000:
                    preview = preview[:2000] + "..."

                return ToolResult(
                    success=True,
                    data={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response_body,
                        "preview": preview,
                        "duration_ms": round(duration_ms, 2),
                        "content_length": len(response.content),
                    },
                    duration_ms=duration_ms,
                )

        except httpx.TimeoutException:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout}s",
                duration_ms=duration_ms,
            )
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                duration_ms=duration_ms,
            )
        except httpx.RequestError as e:
            duration_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                error=f"Request failed: {e}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.exception("ApiDebugTool unexpected error")
            return ToolResult(
                success=False,
                error=f"Unexpected error: {e}",
                duration_ms=duration_ms,
            )
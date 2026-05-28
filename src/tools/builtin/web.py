from __future__ import annotations

import html
import re
import time
import urllib.parse
from typing import Any
from urllib.robotparser import RobotFileParser

import httpx

from src.config import get_settings
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class WebTool(ITool):
    """Web search and fetch tool for accessing online content.

    Supports fetching a URL's content (with optional robots.txt
    compliance) and performing web searches via DuckDuckGo HTML
    search. Read-only operations are logged to the audit trail
    but do not require explicit approval.
    """

    def __init__(self) -> None:
        config = get_settings().tools
        self._user_agent = config.web_user_agent
        self._default_timeout = config.web_timeout
        self._default_respect_robots = config.respect_robots

        self._spec = ToolSpec(
            name="web",
            description="Web search and fetch tool. Supports fetching URL content and web search.",
            category="web",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Action to perform: 'get' to fetch a URL, "
                        "'search' to search the web"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="url",
                    type="string",
                    description="URL to fetch (required for action='get')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query (required for action='search')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=self._default_timeout,
                ),
                ToolParameter(
                    name="respect_robots",
                    type="boolean",
                    description="Whether to check robots.txt before fetching",
                    required=False,
                    default=self._default_respect_robots,
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of search results to return",
                    required=False,
                    default=5,
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
        action = params.get("action", "")

        if action not in ("get", "search"):
            errors.append(
                f"Invalid action: '{action}'. Must be 'get' or 'search'."
            )

        if action == "get":
            url = params.get("url")
            if not url or not isinstance(url, str) or not url.strip():
                errors.append("'url' is required for action='get'")
            else:
                parsed = urllib.parse.urlparse(url.strip())
                if parsed.scheme not in ("http", "https"):
                    errors.append(
                        f"Invalid URL scheme: '{parsed.scheme}'. "
                        "Only http and https are supported."
                    )

        if action == "search":
            query = params.get("query")
            if not query or not isinstance(query, str) or not query.strip():
                errors.append("'query' is required for action='search'")

        timeout = params.get("timeout", self._default_timeout)
        if timeout is not None:
            try:
                t = int(timeout)
                if t < 1 or t > 120:
                    errors.append("'timeout' must be between 1 and 120 seconds")
            except (TypeError, ValueError):
                errors.append("'timeout' must be an integer")

        max_results = params.get("max_results", 5)
        if max_results is not None:
            try:
                mr = int(max_results)
                if mr < 1 or mr > 50:
                    errors.append("'max_results' must be between 1 and 50")
            except (TypeError, ValueError):
                errors.append("'max_results' must be an integer")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the requested web operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with the fetched content or search results.
        """

        action = params.get("action", "")
        timeout = int(params.get("timeout", self._default_timeout))
        respect_robots = bool(
            params.get("respect_robots", self._default_respect_robots)
        )
        max_results = int(params.get("max_results", 5))

        start_time = time.time()

        try:
            if action == "get":
                url = params.get("url", "").strip()
                result = await self._fetch_url(
                    url=url,
                    timeout=timeout,
                    respect_robots=respect_robots,
                )
            else:
                query = params.get("query", "").strip()
                result = await self._search_web(
                    query=query,
                    timeout=timeout,
                    max_results=max_results,
                )

            duration_ms = (time.time() - start_time) * 1000

            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"web_{action}",
                resource=params.get("url") or params.get("query", ""),
                params={
                    "action": action,
                    "timeout": timeout,
                    "max_results": max_results if action == "search" else None,
                },
                result="success" if result.success else "error",
                duration_ms=duration_ms,
                error=result.error if not result.success else "",
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"web_{action}",
                resource=params.get("url") or params.get("query", ""),
                params={"action": action},
                result="error",
                duration_ms=duration_ms,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"Web operation failed: {e}",
                duration_ms=duration_ms,
            )

    async def _fetch_url(
        self,
        url: str,
        timeout: int,
        respect_robots: bool,
    ) -> ToolResult:
        """Fetch content from a URL via HTTP GET.

        Args:
            url: The URL to fetch.
            timeout: Request timeout in seconds.
            respect_robots: Whether to check robots.txt before fetching.

        Returns:
            ToolResult with the page content.
        """

        if respect_robots:
            allowed = await self._check_robots(url)
            if not allowed:
                return ToolResult(
                    success=False,
                    error=(
                        f"Access denied by robots.txt for: {url}"
                    ),
                )

        headers = {
            "User-Agent": self._user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            text = response.text

            return ToolResult(
                success=True,
                data={
                    "url": str(response.url),
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "content": text,
                    "content_length": len(text),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout}s for: {url}",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP {e.response.status_code} for: {url}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Request failed for {url}: {e}",
            )

    async def _search_web(
        self,
        query: str,
        timeout: int,
        max_results: int,
    ) -> ToolResult:
        """Search the web using DuckDuckGo HTML search.

        Args:
            query: The search query string.
            timeout: Request timeout in seconds.
            max_results: Maximum number of results to return.

        Returns:
            ToolResult with a list of search result items.
        """

        encoded_query = urllib.parse.quote(query)
        search_url = (
            f"https://html.duckduckgo.com/html/?q={encoded_query}"
        )

        headers = {
            "User-Agent": self._user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(search_url, headers=headers)
                response.raise_for_status()

            results = self._parse_duckduckgo_results(
                response.text, max_results
            )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": results,
                    "total": len(results),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Search request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Search returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Search request failed: {e}",
            )

    def _parse_duckduckgo_results(
        self,
        html_text: str,
        max_results: int,
    ) -> list[dict[str, str]]:
        """Parse DuckDuckGo HTML search results page.

        Uses regex to extract result blocks from the HTML. Each
        result contains a title, URL, and snippet.

        Args:
            html_text: Raw HTML from DuckDuckGo search results.
            max_results: Maximum number of results to extract.

        Returns:
            List of result dicts with title, url, and snippet keys.
        """

        results: list[dict[str, str]] = []

        result_blocks = re.finditer(
            r'<div[^>]*class="[^"]*\bresult\b[^"]*"[^>]*>.*?'
            r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="([^"]*)"[^>]*>'
            r'(.*?)</a>.*?'
            r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>',
            html_text,
            re.DOTALL,
        )

        for match in result_blocks:
            if len(results) >= max_results:
                break

            href = html.unescape(match.group(1))
            title_raw = html.unescape(
                re.sub(r'<[^>]+>', '', match.group(2))
            )
            snippet_raw = html.unescape(
                re.sub(r'<[^>]+>', '', match.group(3))
            )

            parsed = urllib.parse.urlparse(href)
            actual_url = urllib.parse.parse_qs(
                parsed.query
            ).get("uddg", [href])[0]

            title = ' '.join(title_raw.split())
            snippet = ' '.join(snippet_raw.split())

            results.append({
                "title": title,
                "url": actual_url,
                "snippet": snippet,
            })

        return results

    async def _check_robots(self, url: str) -> bool:
        """Check robots.txt to see if fetching the URL is allowed.

        Args:
            url: The URL to check against robots.txt.

        Returns:
            True if fetching is allowed, False if disallowed.
        """

        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    robots_url,
                    headers={"User-Agent": self._user_agent},
                )

            if response.status_code != 200:
                return True

            rp = RobotFileParser()
            rp.parse(response.text.splitlines())
            return rp.can_fetch(self._user_agent, url)

        except Exception:
            return True

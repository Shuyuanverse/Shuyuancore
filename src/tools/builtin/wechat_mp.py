from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "search_article",
        "get_article",
        "get_account_articles",
    }
)

ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "search_article": {"keyword"},
    "get_article": {"article_url"},
    "get_account_articles": {"account_name"},
}

SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
SOGOU_ACCOUNT_URL = "https://weixin.sogou.com/gzh"


class WeChatMpTool(ITool):
    """WeChat public account articles search and retrieval tool.

    Provides read-only access to public WeChat articles via
    Sogou WeChat search. Supports article search by keyword,
    article content retrieval by URL, and listing articles
    from a specific official account.
    """

    MIN_REQUEST_INTERVAL: float = 1.0

    allow_write: bool = False

    def __init__(self) -> None:
        self._last_request_time: float = 0.0

        self._spec = ToolSpec(
            name="wechat_mp",
            description=(
                "WeChat public account articles tool. Search "
                "articles, get article content by URL, and list "
                "articles from an official account. Read-only."
            ),
            category="social",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=("Action: search_article/get_article/get_account_articles"),
                    required=True,
                ),
                ToolParameter(
                    name="keyword",
                    type="string",
                    description=("Search keyword, required for search_article"),
                    required=False,
                ),
                ToolParameter(
                    name="article_url",
                    type="string",
                    description=("Article URL, required for get_article"),
                    required=False,
                ),
                ToolParameter(
                    name="account_name",
                    type="string",
                    description=("Official account name, required for get_account_articles"),
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return",
                    required=False,
                    default=10,
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

    async def _enforce_rate_limit(self) -> None:
        """Enforce minimum interval between consecutive requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors: list[str] = []
        action = params.get("action", "").strip()

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

        limit = params.get("limit", 10)
        if limit is not None:
            try:
                lv = int(limit)
                if lv < 1 or lv > 100:
                    errors.append("'limit' must be between 1 and 100")
            except (TypeError, ValueError):
                errors.append("'limit' must be an integer")

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
        """Execute the requested WeChat MP data operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with the operation outcome.
        """
        start = time.time()
        action = params.get("action", "")
        timeout = int(params.get("timeout", 30))
        limit = int(params.get("limit", 10))

        await self._enforce_rate_limit()

        try:
            result: ToolResult
            if action == "search_article":
                keyword = params.get("keyword", "").strip()
                result = await self._search_article(keyword, timeout, limit)
            elif action == "get_article":
                article_url = params.get("article_url", "").strip()
                result = await self._get_article(article_url, timeout)
            elif action == "get_account_articles":
                account_name = params.get("account_name", "").strip()
                result = await self._get_account_articles(account_name, timeout, limit)
            else:
                result = ToolResult(success=False, error=f"Unknown action: {action}")

            result.duration_ms = (time.time() - start) * 1000
            return result

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"WeChat MP operation failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _search_article(
        self,
        keyword: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """Search public WeChat articles by keyword via Sogou.

        Args:
            keyword: Search query string.
            timeout: Request timeout in seconds.
            limit: Maximum number of results to return.

        Returns:
            ToolResult with list of matching articles.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

        params = {
            "query": keyword,
            "type": "2",
            "page": "1",
            "ie": "utf8",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    SOGOU_SEARCH_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

            text = response.text
            articles = self._parse_sogou_results(text, limit)

            return ToolResult(
                success=True,
                data={
                    "keyword": keyword,
                    "articles": articles,
                    "total": len(articles),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Article search timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Article search returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Article search request failed: {e}",
            )

    def _parse_sogou_results(
        self,
        html_text: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Parse Sogou WeChat search results HTML into structured data.

        Args:
            html_text: Raw HTML from Sogou WeChat search results.
            max_results: Maximum number of results to extract.

        Returns:
            List of article dicts with title, url, account, and summary.
        """
        articles: list[dict[str, Any]] = []

        item_pattern = re.compile(
            r'<div[^>]*class="[^"]*wx-rb[^"]*"[^>]*>.*?'
            r'<a[^>]*href="([^"]*)"[^>]*target="_blank"',
            re.DOTALL,
        )

        for item_match in item_pattern.finditer(html_text):
            if len(articles) >= max_results:
                break

            item_html = item_match.group(0)

            href = item_match.group(1).strip()
            full_url = f"https:{href}" if href.startswith("//") else href

            title_pattern = re.compile(r"<h3[^>]*>.*?<a[^>]*>(.*?)</a>", re.DOTALL)
            title_match = title_pattern.search(item_html)
            title = ""
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

            account_pattern = re.compile(
                r'<a[^>]*class="[^"]*account[^"]*"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            account_match = account_pattern.search(item_html)
            account = ""
            if account_match:
                account = re.sub(r"<[^>]+>", "", account_match.group(1)).strip()

            summary_pattern = re.compile(
                r'<p[^>]*class="[^"]*txt-info[^"]*"[^>]*>(.*?)</p>',
                re.DOTALL,
            )
            summary_match = summary_pattern.search(item_html)
            summary = ""
            if summary_match:
                summary = re.sub(r"<[^>]+>", "", summary_match.group(1)).strip()

            articles.append(
                {
                    "title": title,
                    "url": full_url,
                    "account": account,
                    "summary": summary,
                }
            )

        return articles

    async def _get_article(
        self,
        article_url: str,
        timeout: int,
    ) -> ToolResult:
        """Get the content of a WeChat article by its URL.

        Fetches the article page and extracts the main content,
        title, and publish time from the HTML.

        Args:
            article_url: The URL of the WeChat article.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the article content.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(article_url, headers=headers)
                response.raise_for_status()

            text = response.text

            title = ""
            title_pattern = re.compile(
                r'<h1[^>]*class="[^"]*rich_media_title[^"]*"[^>]*>'
                r"(.*?)</h1>",
                re.DOTALL,
            )
            title_match = title_pattern.search(text)
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

            content = ""
            content_pattern = re.compile(
                r'<div[^>]*class="[^"]*rich_media_content[^"]*"[^>]*>'
                r"(.*?)</div>",
                re.DOTALL,
            )
            content_match = content_pattern.search(text)
            if content_match:
                content_raw = content_match.group(1)
                content = re.sub(r"<[^>]+>", "", content_raw)
                content = re.sub(r"\s+", " ", content).strip()

            publish_time = ""
            time_pattern = re.compile(
                r'<em[^>]*class="[^"]*rich_media_meta_text[^"]*"[^>]*>'
                r"(\d{4}[\d-:\s]+)",
            )
            time_match = time_pattern.search(text)
            if time_match:
                publish_time = time_match.group(1).strip()

            account_name = ""
            account_pattern = re.compile(
                r'<strong[^>]*class="[^"]*rich_media_meta_nickname'
                r'[^"]*"[^>]*>(.*?)</strong>',
                re.DOTALL,
            )
            account_match = account_pattern.search(text)
            if account_match:
                account_name = re.sub(r"<[^>]+>", "", account_match.group(1)).strip()

            if not content:
                return ToolResult(
                    success=False,
                    error=(
                        "Could not extract article content. "
                        "The URL may be invalid or require login."
                    ),
                )

            return ToolResult(
                success=True,
                data={
                    "title": title,
                    "content": content[:10000],
                    "publish_time": publish_time,
                    "account_name": account_name,
                    "url": article_url,
                    "content_length": len(content),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get article timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Get article returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Get article request failed: {e}",
            )

    async def _get_account_articles(
        self,
        account_name: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """List recent articles from a WeChat official account.

        Searches for the account on Sogou WeChat and retrieves
        its recent published articles.

        Args:
            account_name: The name of the official account.
            timeout: Request timeout in seconds.
            limit: Maximum number of articles to return.

        Returns:
            ToolResult with list of articles from the account.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

        params = {
            "query": account_name,
            "type": "1",
            "page": "1",
            "ie": "utf8",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    SOGOU_SEARCH_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

            text = response.text
            account_link_pattern = re.compile(
                r'<a[^>]*href="(//weixin\.sogou\.com/gzh\?[^"]+)"'
                r"[^>]*>.*?</a>",
                re.DOTALL,
            )

            account_url = ""
            for link_match in account_link_pattern.finditer(text):
                href = link_match.group(1).strip()
                if (
                    account_name in href
                    or account_name in text[max(0, link_match.start() - 200) : link_match.end()]
                ):
                    account_url = f"https:{href}"
                    break

            if not account_url:
                return ToolResult(
                    success=False,
                    error=(f"Account '{account_name}' not found on Sogou WeChat"),
                )

            await self._enforce_rate_limit()

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                account_resp = await client.get(account_url, headers=headers)
                account_resp.raise_for_status()

            account_text = account_resp.text
            articles: list[dict[str, Any]] = []

            article_pattern = re.compile(
                r'<div[^>]*class="[^"]*wx-rb[^"]*"[^>]*>.*?'
                r'<a[^>]*href="([^"]*)"[^>]*target="_blank"',
                re.DOTALL,
            )

            for art_match in article_pattern.finditer(account_text):
                if len(articles) >= limit:
                    break

                art_html = art_match.group(0)
                href = art_match.group(1).strip()
                full_url = f"https:{href}" if href.startswith("//") else href

                title_match = re.search(
                    r"<h3[^>]*>.*?<a[^>]*>(.*?)</a>",
                    art_html,
                    re.DOTALL,
                )
                title = ""
                if title_match:
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

                summary_match = re.search(
                    r'<p[^>]*class="[^"]*txt-info[^"]*"[^>]*>'
                    r"(.*?)</p>",
                    art_html,
                    re.DOTALL,
                )
                summary = ""
                if summary_match:
                    summary = re.sub(r"<[^>]+>", "", summary_match.group(1)).strip()

                time_match = re.search(r"(\d{4}-\d{2}-\d{2})", art_html)

                articles.append(
                    {
                        "title": title,
                        "url": full_url,
                        "summary": summary,
                        "date": (time_match.group(1) if time_match else ""),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "account_name": account_name,
                    "articles": articles,
                    "total": len(articles),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=(f"Get account articles timed out after {timeout}s"),
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Get account articles returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=(f"Get account articles request failed: {e}"),
            )

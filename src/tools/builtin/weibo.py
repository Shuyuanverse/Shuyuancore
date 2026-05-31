from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "search_weibo",
        "get_weibo",
        "search_user",
        "get_user_weibos",
        "get_comments",
    }
)

ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "search_weibo": {"keyword"},
    "get_weibo": {"weibo_id"},
    "search_user": {"keyword"},
    "get_user_weibos": {"user_id"},
    "get_comments": {"weibo_id"},
}

SEARCH_URL = "https://s.weibo.com/weibo"
WEIBO_DETAIL_URL = "https://m.weibo.cn/detail"
USER_SEARCH_URL = "https://s.weibo.com/user"
USER_WEIBOS_URL = "https://m.weibo.cn/api/container/getIndex"
COMMENTS_URL = "https://m.weibo.cn/api/comments/show"


class WeiBoTool(ITool):
    """Weibo public data search and retrieval tool.

    Provides read-only access to public Weibo data including
    post search, post detail, user search, user posts listing,
    and comment retrieval. All operations use public web
    interfaces and do not require authentication.

    WARNING / 警告:
    This tool uses unofficial API interfaces. In production, you
    MUST use the official Weibo Open Platform API with a valid
    API Key.
    本工具使用非官方 API 接口。生产环境中必须使用微博开放平台
    官方 API，并配置有效的 API Key。
    """

    MIN_REQUEST_INTERVAL: float = 1.0

    allow_write: bool = False
    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._last_request_time: float = 0.0

        self._spec = ToolSpec(
            name="weibo",
            description=(
                "Weibo public data tool. Search posts, get post "
                "details, search users, list user posts, and get "
                "comments. Read-only by default."
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Action: search_weibo/get_weibo/search_user/get_user_weibos/get_comments"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="keyword",
                    type="string",
                    description=("Search keyword, required for search_weibo and search_user"),
                    required=False,
                ),
                ToolParameter(
                    name="weibo_id",
                    type="string",
                    description=("Weibo post ID, required for get_weibo and get_comments"),
                    required=False,
                ),
                ToolParameter(
                    name="user_id",
                    type="string",
                    description=("Weibo user ID, required for get_user_weibos"),
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
        """Execute the requested Weibo data operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with the operation outcome.
        """
        if not self._USE_OFFICIAL_API:
            return ToolResult(
                success=False,
                output="该功能需要配置官方 API Key / This feature requires official API key configuration",
                error="Official API not configured",
            )

        start = time.time()
        action = params.get("action", "")
        timeout = int(params.get("timeout", 30))
        limit = int(params.get("limit", 10))

        await self._enforce_rate_limit()

        try:
            result: ToolResult
            if action == "search_weibo":
                keyword = params.get("keyword", "").strip()
                result = await self._search_weibo(keyword, timeout, limit)
            elif action == "get_weibo":
                weibo_id = params.get("weibo_id", "").strip()
                result = await self._get_weibo(weibo_id, timeout)
            elif action == "search_user":
                keyword = params.get("keyword", "").strip()
                result = await self._search_user(keyword, timeout, limit)
            elif action == "get_user_weibos":
                user_id = params.get("user_id", "").strip()
                result = await self._get_user_weibos(user_id, timeout, limit)
            elif action == "get_comments":
                weibo_id = params.get("weibo_id", "").strip()
                result = await self._get_comments(weibo_id, timeout, limit)
            else:
                result = ToolResult(success=False, error=f"Unknown action: {action}")

            result.duration_ms = (time.time() - start) * 1000
            return result

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Weibo operation failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _search_weibo(
        self,
        keyword: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """Search public Weibo posts by keyword.

        Args:
            keyword: Search query string.
            timeout: Request timeout in seconds.
            limit: Maximum number of results to return.

        Returns:
            ToolResult with list of matching posts.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

        params = {"q": keyword, "typeall": "1", "page": "1"}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(SEARCH_URL, params=params, headers=headers)
                response.raise_for_status()

            text = response.text
            posts = self._parse_search_results(text, limit)

            return ToolResult(
                success=True,
                data={
                    "keyword": keyword,
                    "posts": posts,
                    "total": len(posts),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Weibo search timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Weibo search returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Weibo search request failed: {e}",
            )

    def _parse_search_results(
        self,
        html_text: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Parse Weibo search results HTML into structured data.

        Args:
            html_text: Raw HTML from Weibo search results page.
            max_results: Maximum number of results to extract.

        Returns:
            List of post dicts with id, text, user, time, and url keys.
        """
        posts: list[dict[str, Any]] = []

        card_pattern = re.compile(
            r'<div[^>]*class="[^"]*card-wrap[^"]*"[^>]*>.*?'
            r'<p[^>]*class="[^"]*txt[^"]*"[^>]*>(.*?)</p>',
            re.DOTALL,
        )

        for match in card_pattern.finditer(html_text):
            if len(posts) >= max_results:
                break

            content_html = match.group(1)
            text = re.sub(r"<[^>]+>", "", content_html)
            text = text.strip()

            mid_match = re.search(r"weibo_id=(\d+)", content_html)
            weibo_id = mid_match.group(1) if mid_match else ""

            url_match = re.search(r'href="(//weibo\.com/\d+/[^"]+)"', content_html)
            url = f"https:{url_match.group(1)}" if url_match else ""

            posts.append(
                {
                    "id": weibo_id,
                    "text": text,
                    "url": url,
                }
            )

        return posts

    async def _get_weibo(
        self,
        weibo_id: str,
        timeout: int,
    ) -> ToolResult:
        """Get a single Weibo post detail by ID.

        Args:
            weibo_id: The Weibo post ID.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the post detail data.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://m.weibo.cn/detail/{weibo_id}",
            "X-Requested-With": "XMLHttpRequest",
        }

        url = f"{WEIBO_DETAIL_URL}/{weibo_id}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            text = response.text
            card_pattern = re.compile(
                r'<div[^>]*class="[^"]*card[^"]*"[^>]*>.*?'
                r'<div[^>]*class="[^"]*weibo-text[^"]*"[^>]*>'
                r"(.*?)</div>",
                re.DOTALL,
            )

            content = ""
            card_match = card_pattern.search(text)
            if card_match:
                content = re.sub(r"<[^>]+>", "", card_match.group(1))
                content = content.strip()

            return ToolResult(
                success=True,
                data={
                    "id": weibo_id,
                    "content": content or "Content not found",
                    "url": f"https://weibo.com/{weibo_id}",
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get weibo timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Get weibo returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Get weibo request failed: {e}",
            )

    async def _search_user(
        self,
        keyword: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """Search Weibo users by keyword.

        Args:
            keyword: User search query string.
            timeout: Request timeout in seconds.
            limit: Maximum number of results to return.

        Returns:
            ToolResult with list of matching users.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

        params = {"q": keyword}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(USER_SEARCH_URL, params=params, headers=headers)
                response.raise_for_status()

            text = response.text
            users: list[dict[str, str]] = []

            user_pattern = re.compile(
                r'<div[^>]*class="[^"]*card-user[^"]*"[^>]*>.*?'
                r'<a[^>]*href="([^"]*)"[^>]*>.*?'
                r"<strong[^>]*>(.*?)</strong>",
                re.DOTALL,
            )

            for match in user_pattern.finditer(text):
                if len(users) >= limit:
                    break
                href = match.group(1).strip()
                name = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                full_url = f"https:{href}" if href.startswith("//") else href
                users.append(
                    {
                        "name": name,
                        "url": full_url,
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "keyword": keyword,
                    "users": users,
                    "total": len(users),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"User search timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"User search returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"User search request failed: {e}",
            )

    async def _get_user_weibos(
        self,
        user_id: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """List Weibo posts from a specific user.

        Uses the mobile API to fetch a user's post container.

        Args:
            user_id: The Weibo user ID.
            timeout: Request timeout in seconds.
            limit: Maximum number of posts to return.

        Returns:
            ToolResult with list of user's posts.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://m.weibo.cn/u/{user_id}",
            "X-Requested-With": "XMLHttpRequest",
        }

        params = {
            "type": "uid",
            "value": user_id,
            "containerid": f"107603{user_id}",
            "page": "1",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    USER_WEIBOS_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

            data = response.json()
            cards = data.get("data", {}).get("cards", [])
            posts: list[dict[str, Any]] = []

            for card in cards:
                if len(posts) >= limit:
                    break
                mblog = card.get("mblog")
                if not mblog:
                    continue

                posts.append(
                    {
                        "id": mblog.get("id", ""),
                        "text": mblog.get("text", ""),
                        "created_at": mblog.get("created_at", ""),
                        "reposts_count": mblog.get("reposts_count", 0),
                        "comments_count": mblog.get("comments_count", 0),
                        "attitudes_count": mblog.get("attitudes_count", 0),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "user_id": user_id,
                    "posts": posts,
                    "total": len(posts),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get user weibos timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Get user weibos returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Get user weibos request failed: {e}",
            )
        except ValueError:
            return ToolResult(
                success=False,
                error="Failed to parse user weibos response as JSON",
            )

    async def _get_comments(
        self,
        weibo_id: str,
        timeout: int,
        limit: int,
    ) -> ToolResult:
        """Get comments of a Weibo post.

        Uses the mobile API to fetch comments for a given post.

        Args:
            weibo_id: The Weibo post ID.
            timeout: Request timeout in seconds.
            limit: Maximum number of comments to return.

        Returns:
            ToolResult with list of comments.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://m.weibo.cn/detail/{weibo_id}",
            "X-Requested-With": "XMLHttpRequest",
        }

        params = {"id": weibo_id, "page": "1"}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    COMMENTS_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

            data = response.json()
            raw_comments = data.get("data", [])
            comments: list[dict[str, Any]] = []

            for cmt in raw_comments:
                if len(comments) >= limit:
                    break
                user = cmt.get("user", {})
                comments.append(
                    {
                        "id": cmt.get("id", ""),
                        "text": cmt.get("text", ""),
                        "created_at": cmt.get("created_at", ""),
                        "user": {
                            "id": user.get("id", ""),
                            "screen_name": user.get("screen_name", ""),
                        },
                        "like_count": cmt.get("like_count", 0),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "weibo_id": weibo_id,
                    "comments": comments,
                    "total": len(comments),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get comments timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=(f"Get comments returned HTTP {e.response.status_code}"),
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Get comments request failed: {e}",
            )
        except ValueError:
            return ToolResult(
                success=False,
                error="Failed to parse comments response as JSON",
            )

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class XiaoHongShuTool(ITool):
    """小红书 public data tool (read-only by default).

    Supports searching public notes, fetching note details, searching
    users, and retrieving user comments. Operates in read-only mode
    with a configurable rate limiter to respect platform frequency
    limits.

    Future extension: set `allow_write = True` to enable write
    operations (requires platform API credentials).

    WARNING / 警告:
    This tool uses unofficial API interfaces. In production, you
    MUST use the official Xiaohongshu Open Platform API with a
    valid API Key.
    本工具使用非官方 API 接口。生产环境中必须使用小红书开放平台
    官方 API，并配置有效的 API Key。
    """

    allow_write: bool = False
    MIN_REQUEST_INTERVAL: float = 1.0
    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="xiaohongshu",
            description=(
                "小红书 public data tool. Supports searching notes, "
                "fetching note details, searching users, and getting "
                "user comments. Read-only by default."
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Action to perform: 'search_note', 'get_note', "
                        "'search_user', or 'get_user_comments'"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="keyword",
                    type="string",
                    description="Search keyword (required for 'search_note' and 'search_user')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="note_id",
                    type="string",
                    description="Note ID (required for 'get_note' and 'get_user_comments')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="user_id",
                    type="string",
                    description="User ID (required for 'search_user')",
                    required=False,
                    default=None,
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
        self._last_request_time: float = 0.0

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

        valid_actions = ("search_note", "get_note", "search_user", "get_user_comments")
        if action not in valid_actions:
            errors.append(f"Invalid action: '{action}'. Must be one of {valid_actions}.")

        if action == "search_note":
            keyword = params.get("keyword")
            if not keyword or not isinstance(keyword, str) or not keyword.strip():
                errors.append("'keyword' is required for action='search_note'")

        if action == "get_note":
            note_id = params.get("note_id")
            if not note_id or not isinstance(note_id, str) or not note_id.strip():
                errors.append("'note_id' is required for action='get_note'")

        if action == "search_user":
            keyword = params.get("keyword")
            if not keyword or not isinstance(keyword, str) or not keyword.strip():
                errors.append("'keyword' is required for action='search_user'")

        if action == "get_user_comments":
            note_id = params.get("note_id")
            if not note_id or not isinstance(note_id, str) or not note_id.strip():
                errors.append("'note_id' is required for action='get_user_comments'")

        limit = params.get("limit", 10)
        if limit is not None:
            try:
                lv = int(limit)
                if lv < 1 or lv > 50:
                    errors.append("'limit' must be between 1 and 50")
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
        """Execute the requested Xiaohongshu operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with the requested data or error information.
        """
        if not self._USE_OFFICIAL_API:
            return ToolResult(
                success=False,
                output="该功能需要配置官方 API Key / This feature requires official API key configuration",
                error="Official API not configured",
            )

        action = params.get("action", "")
        limit = int(params.get("limit", 10))
        timeout = int(params.get("timeout", 30))

        await self._rate_limit()

        start_time = time.time()

        try:
            if action == "search_note":
                keyword = params.get("keyword", "").strip()
                result = await self._search_notes(
                    keyword=keyword,
                    limit=limit,
                    timeout=timeout,
                )
            elif action == "get_note":
                note_id = params.get("note_id", "").strip()
                result = await self._get_note(
                    note_id=note_id,
                    timeout=timeout,
                )
            elif action == "search_user":
                keyword = params.get("keyword", "").strip()
                result = await self._search_users(
                    keyword=keyword,
                    limit=limit,
                    timeout=timeout,
                )
            else:
                note_id = params.get("note_id", "").strip()
                result = await self._get_comments(
                    note_id=note_id,
                    limit=limit,
                    timeout=timeout,
                )

            duration_ms = (time.time() - start_time) * 1000
            result.duration_ms = duration_ms

            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"xiaohongshu_{action}",
                resource=(
                    params.get("keyword") or params.get("note_id") or params.get("user_id", "")
                ),
                params={
                    "action": action,
                    "limit": limit,
                    "timeout": timeout,
                },
                result="success" if result.success else "error",
                duration_ms=duration_ms,
                error=result.error if not result.success else "",
            )

            return result

        except Exception as e:
            logger.exception("xiaohongshu operation failed: action=%s", action)
            duration_ms = (time.time() - start_time) * 1000
            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"xiaohongshu_{action}",
                resource=(params.get("keyword") or params.get("note_id", "")),
                params={"action": action},
                result="error",
                duration_ms=duration_ms,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"Xiaohongshu operation failed: {e}",
                duration_ms=duration_ms,
            )

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between consecutive requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    async def _search_notes(
        self,
        keyword: str,
        limit: int,
        timeout: int,
    ) -> ToolResult:
        """Search public notes by keyword.

        Uses simulated/mock API responses. In production, replace
        with actual Xiaohongshu API calls via httpx.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with a list of matching notes.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                params: dict[str, str] = {
                    "keyword": keyword,
                    "limit": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
                    params=params,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "keyword": keyword,
                        "notes": data.get("items", data.get("data", [])),
                        "total": len(data.get("items", data.get("data", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Search notes request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403 or e.response.status_code == 404:
                return self._mock_search_notes(keyword, limit)
            return ToolResult(
                success=False,
                error=f"Search notes returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_search_notes(keyword, limit)
        except Exception:
            logger.exception("Unexpected error in search_notes, falling back to mock")
            return self._mock_search_notes(keyword, limit)

    def _mock_search_notes(
        self,
        keyword: str,
        limit: int,
    ) -> ToolResult:
        """Return simulated search results when API is unavailable.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.

        Returns:
            ToolResult with mock note data.
        """
        notes = [
            {
                "note_id": "note_001",
                "title": f"{keyword} - 精选推荐",
                "author": "小红书用户1",
                "likes": 1234,
                "comments": 56,
                "summary": f"这是一篇关于{keyword}的精选内容...",
            },
            {
                "note_id": "note_002",
                "title": f"{keyword} - 热门攻略",
                "author": "小红书用户2",
                "likes": 890,
                "comments": 34,
                "summary": f"详细{keyword}攻略分享，包含实用技巧...",
            },
            {
                "note_id": "note_003",
                "title": f"{keyword} - 经验分享",
                "author": "小红书用户3",
                "likes": 567,
                "comments": 12,
                "summary": f"{keyword}经验总结，避免踩坑...",
            },
        ]
        return ToolResult(
            success=True,
            data={
                "keyword": keyword,
                "notes": notes[:limit],
                "total": min(len(notes), limit),
                "source": "mock",
            },
        )

    async def _get_note(
        self,
        note_id: str,
        timeout: int,
    ) -> ToolResult:
        """Get note detail by note_id.

        Args:
            note_id: The unique identifier of the note.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the full note details.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    f"https://edith.xiaohongshu.com/api/sns/web/v1/feed?note_id={note_id}",
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "note_id": note_id,
                        "detail": data.get("items", data.get("data", {})),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get note request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403 or e.response.status_code == 404:
                return self._mock_get_note(note_id)
            return ToolResult(
                success=False,
                error=f"Get note returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_get_note(note_id)
        except Exception:
            logger.exception("Unexpected error in get_note, falling back to mock")
            return self._mock_get_note(note_id)

    def _mock_get_note(
        self,
        note_id: str,
    ) -> ToolResult:
        """Return simulated note detail when API is unavailable.

        Args:
            note_id: The note identifier.

        Returns:
            ToolResult with mock note detail data.
        """
        return ToolResult(
            success=True,
            data={
                "note_id": note_id,
                "title": "笔记标题示例",
                "content": "这是笔记的详细内容，包含图片和文字描述...",
                "author": "小红书用户",
                "likes": 1234,
                "comments": 56,
                "collections": 789,
                "tags": ["tag1", "tag2"],
                "created_at": 1700000000000,
                "images": [
                    "https://example.com/image1.jpg",
                    "https://example.com/image2.jpg",
                ],
                "source": "mock",
            },
        )

    async def _search_users(
        self,
        keyword: str,
        limit: int,
        timeout: int,
    ) -> ToolResult:
        """Search users by keyword.

        Args:
            keyword: Search keyword for user lookup.
            limit: Maximum number of results.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with a list of matching users.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                params: dict[str, str] = {
                    "keyword": keyword,
                    "limit": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://edith.xiaohongshu.com/api/sns/web/v1/search/users",
                    params=params,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "keyword": keyword,
                        "users": data.get("items", data.get("data", [])),
                        "total": len(data.get("items", data.get("data", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Search users request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403 or e.response.status_code == 404:
                return self._mock_search_users(keyword, limit)
            return ToolResult(
                success=False,
                error=f"Search users returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_search_users(keyword, limit)
        except Exception:
            logger.exception("Unexpected error in search_users, falling back to mock")
            return self._mock_search_users(keyword, limit)

    def _mock_search_users(
        self,
        keyword: str,
        limit: int,
    ) -> ToolResult:
        """Return simulated user search results when API is unavailable.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.

        Returns:
            ToolResult with mock user data.
        """
        users = [
            {
                "user_id": "user_001",
                "nickname": f"{keyword}_达人1",
                "followers": 12345,
                "notes_count": 89,
                "description": f"{keyword}领域优质创作者",
            },
            {
                "user_id": "user_002",
                "nickname": f"{keyword}_达人2",
                "followers": 6789,
                "notes_count": 45,
                "description": f"分享{keyword}相关经验",
            },
            {
                "user_id": "user_003",
                "nickname": f"{keyword}_爱好者",
                "followers": 1234,
                "notes_count": 23,
                "description": f"{keyword}爱好者，持续更新",
            },
        ]
        return ToolResult(
            success=True,
            data={
                "keyword": keyword,
                "users": users[:limit],
                "total": min(len(users), limit),
                "source": "mock",
            },
        )

    async def _get_comments(
        self,
        note_id: str,
        limit: int,
        timeout: int,
    ) -> ToolResult:
        """Get comments of a note by note_id.

        Args:
            note_id: The note identifier to fetch comments for.
            limit: Maximum number of comments to return.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the list of comments.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                params: dict[str, str] = {
                    "note_id": note_id,
                    "limit": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://edith.xiaohongshu.com/api/sns/web/v1/comment/page",
                    params=params,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "note_id": note_id,
                        "comments": data.get("items", data.get("data", [])),
                        "total": len(data.get("items", data.get("data", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get comments request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403 or e.response.status_code == 404:
                return self._mock_get_comments(note_id, limit)
            return ToolResult(
                success=False,
                error=f"Get comments returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_get_comments(note_id, limit)
        except Exception:
            logger.exception("Unexpected error in get_comments, falling back to mock")
            return self._mock_get_comments(note_id, limit)

    def _mock_get_comments(
        self,
        note_id: str,
        limit: int,
    ) -> ToolResult:
        """Return simulated comments when API is unavailable.

        Args:
            note_id: The note identifier.
            limit: Maximum number of comments.

        Returns:
            ToolResult with mock comment data.
        """
        comments = [
            {
                "comment_id": "comment_001",
                "user": "用户A",
                "content": "写得很好，收藏了！",
                "likes": 123,
                "created_at": 1700000000000,
            },
            {
                "comment_id": "comment_002",
                "user": "用户B",
                "content": "请问这个在哪里可以买到？",
                "likes": 45,
                "created_at": 1700000001000,
            },
            {
                "comment_id": "comment_003",
                "user": "用户C",
                "content": "感谢分享，很有帮助！",
                "likes": 67,
                "created_at": 1700000002000,
            },
            {
                "comment_id": "comment_004",
                "user": "用户D",
                "content": "同求链接，谢谢楼主",
                "likes": 23,
                "created_at": 1700000003000,
            },
            {
                "comment_id": "comment_005",
                "user": "用户E",
                "content": "已关注，期待更多内容",
                "likes": 89,
                "created_at": 1700000004000,
            },
        ]
        return ToolResult(
            success=True,
            data={
                "note_id": note_id,
                "comments": comments[:limit],
                "total": min(len(comments), limit),
                "source": "mock",
            },
        )

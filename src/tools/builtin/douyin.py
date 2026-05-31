from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class DouYinTool(ITool):
    """抖音 public data tool (read-only by default).

    Supports searching public videos, fetching video details, searching
    users, and listing user videos. Operates in read-only mode with a
    configurable rate limiter to respect platform frequency limits.

    Future extension: set `allow_write = True` to enable write
    operations (requires platform API credentials).

    WARNING / 警告:
    This tool uses unofficial API interfaces. In production, you
    MUST use the official Douyin Open Platform API with a valid
    API Key.
    本工具使用非官方 API 接口。生产环境中必须使用抖音开放平台
    官方 API，并配置有效的 API Key。
    """

    allow_write: bool = False
    MIN_REQUEST_INTERVAL: float = 1.0
    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="douyin",
            description=(
                "抖音 public data tool. Supports searching videos, "
                "fetching video details, searching users, and listing "
                "user videos. Read-only by default."
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Action to perform: 'search_video', 'get_video', "
                        "'search_user', or 'get_user_videos'"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="keyword",
                    type="string",
                    description="Search keyword (required for 'search_video' and 'search_user')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="video_id",
                    type="string",
                    description="Video ID (required for 'get_video')",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="user_id",
                    type="string",
                    description="User ID (required for 'search_user' and 'get_user_videos')",
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

        valid_actions = ("search_video", "get_video", "search_user", "get_user_videos")
        if action not in valid_actions:
            errors.append(f"Invalid action: '{action}'. Must be one of {valid_actions}.")

        if action == "search_video":
            keyword = params.get("keyword")
            if not keyword or not isinstance(keyword, str) or not keyword.strip():
                errors.append("'keyword' is required for action='search_video'")

        if action == "get_video":
            video_id = params.get("video_id")
            if not video_id or not isinstance(video_id, str) or not video_id.strip():
                errors.append("'video_id' is required for action='get_video'")

        if action == "search_user":
            keyword = params.get("keyword")
            if not keyword or not isinstance(keyword, str) or not keyword.strip():
                errors.append("'keyword' is required for action='search_user'")

        if action == "get_user_videos":
            user_id = params.get("user_id")
            if not user_id or not isinstance(user_id, str) or not user_id.strip():
                errors.append("'user_id' is required for action='get_user_videos'")

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
        """Execute the requested Douyin operation.

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
            if action == "search_video":
                keyword = params.get("keyword", "").strip()
                result = await self._search_videos(
                    keyword=keyword,
                    limit=limit,
                    timeout=timeout,
                )
            elif action == "get_video":
                video_id = params.get("video_id", "").strip()
                result = await self._get_video(
                    video_id=video_id,
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
                user_id = params.get("user_id", "").strip()
                result = await self._get_user_videos(
                    user_id=user_id,
                    limit=limit,
                    timeout=timeout,
                )

            duration_ms = (time.time() - start_time) * 1000
            result.duration_ms = duration_ms

            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"douyin_{action}",
                resource=(
                    params.get("keyword") or params.get("video_id") or params.get("user_id", "")
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
            duration_ms = (time.time() - start_time) * 1000
            audit = get_audit_logger()
            audit.log(
                user_id=user_id,
                action=f"douyin_{action}",
                resource=(params.get("keyword") or params.get("video_id", "")),
                params={"action": action},
                result="error",
                duration_ms=duration_ms,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"Douyin operation failed: {e}",
                duration_ms=duration_ms,
            )

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between consecutive requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    async def _search_videos(
        self,
        keyword: str,
        limit: int,
        timeout: int,
    ) -> ToolResult:
        """Search public videos by keyword.

        Uses simulated/mock API responses. In production, replace
        with actual Douyin API calls via httpx.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with a list of matching videos.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                params: dict[str, str] = {
                    "keyword": keyword,
                    "count": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://www.douyin.com/aweme/v1/web/search/item/",
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
                        "videos": data.get("data", data.get("item_list", [])),
                        "total": len(data.get("data", data.get("item_list", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Search videos request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return self._mock_search_videos(keyword, limit)
            return ToolResult(
                success=False,
                error=f"Search videos returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_search_videos(keyword, limit)
        except Exception:
            return self._mock_search_videos(keyword, limit)

    def _mock_search_videos(
        self,
        keyword: str,
        limit: int,
    ) -> ToolResult:
        """Return simulated search results when API is unavailable.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.

        Returns:
            ToolResult with mock video data.
        """
        videos = [
            {
                "video_id": "video_001",
                "title": f"{keyword} - 热门推荐",
                "author": "抖音达人1",
                "likes": 5678,
                "comments": 234,
                "shares": 123,
                "duration": 120,
                "description": f"这是一条关于{keyword}的热门视频...",
            },
            {
                "video_id": "video_002",
                "title": f"{keyword} - 教程分享",
                "author": "抖音达人2",
                "likes": 3456,
                "comments": 178,
                "shares": 89,
                "duration": 180,
                "description": f"{keyword}详细教程，手把手教学...",
            },
            {
                "video_id": "video_003",
                "title": f"{keyword} - 精彩合集",
                "author": "抖音达人3",
                "likes": 2345,
                "comments": 98,
                "shares": 56,
                "duration": 90,
                "description": f"{keyword}精彩瞬间合集...",
            },
        ]
        return ToolResult(
            success=True,
            data={
                "keyword": keyword,
                "videos": videos[:limit],
                "total": min(len(videos), limit),
                "source": "mock",
            },
        )

    async def _get_video(
        self,
        video_id: str,
        timeout: int,
    ) -> ToolResult:
        """Get video detail by video_id.

        Args:
            video_id: The unique identifier of the video.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the full video details.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    f"https://www.douyin.com/aweme/v1/web/item/detail/?item_id={video_id}",
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
                        "video_id": video_id,
                        "detail": data.get("item", data.get("data", {})),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get video request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return self._mock_get_video(video_id)
            return ToolResult(
                success=False,
                error=f"Get video returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_get_video(video_id)
        except Exception:
            return self._mock_get_video(video_id)

    def _mock_get_video(
        self,
        video_id: str,
    ) -> ToolResult:
        """Return simulated video detail when API is unavailable.

        Args:
            video_id: The video identifier.

        Returns:
            ToolResult with mock video detail data.
        """
        return ToolResult(
            success=True,
            data={
                "video_id": video_id,
                "title": "视频标题示例",
                "description": "这是视频的详细描述内容...",
                "author": "抖音用户",
                "likes": 12345,
                "comments": 678,
                "shares": 234,
                "favorites": 3456,
                "duration": 150,
                "play_count": 98765,
                "created_at": 1700000000000,
                "tags": ["热门", "推荐"],
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
                    "count": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://www.douyin.com/aweme/v1/web/search/user/",
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
                        "users": data.get("data", data.get("user_list", [])),
                        "total": len(data.get("data", data.get("user_list", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Search users request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return self._mock_search_users(keyword, limit)
            return ToolResult(
                success=False,
                error=f"Search users returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_search_users(keyword, limit)
        except Exception:
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
                "nickname": f"{keyword}_创作者1",
                "followers": 98765,
                "following": 234,
                "video_count": 156,
                "description": f"{keyword}领域优质创作者",
                "verified": True,
            },
            {
                "user_id": "user_002",
                "nickname": f"{keyword}_达人",
                "followers": 45678,
                "following": 89,
                "video_count": 78,
                "description": f"分享{keyword}相关精彩内容",
                "verified": False,
            },
            {
                "user_id": "user_003",
                "nickname": f"{keyword}_爱好者",
                "followers": 12345,
                "following": 567,
                "video_count": 45,
                "description": f"{keyword}爱好者，每日更新",
                "verified": False,
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

    async def _get_user_videos(
        self,
        user_id: str,
        limit: int,
        timeout: int,
    ) -> ToolResult:
        """List videos of a user by user_id.

        Args:
            user_id: The user identifier.
            limit: Maximum number of videos to return.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with the list of user's videos.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            ) as client:
                params: dict[str, str] = {
                    "user_id": user_id,
                    "count": str(min(limit, 20)),
                }
                response = await client.get(
                    "https://www.douyin.com/aweme/v1/web/user/post/",
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
                        "user_id": user_id,
                        "videos": data.get("data", data.get("item_list", [])),
                        "total": len(data.get("data", data.get("item_list", []))),
                    },
                )

        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Get user videos request timed out after {timeout}s",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return self._mock_get_user_videos(user_id, limit)
            return ToolResult(
                success=False,
                error=f"Get user videos returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError:
            return self._mock_get_user_videos(user_id, limit)
        except Exception:
            return self._mock_get_user_videos(user_id, limit)

    def _mock_get_user_videos(
        self,
        user_id: str,
        limit: int,
    ) -> ToolResult:
        """Return simulated user videos when API is unavailable.

        Args:
            user_id: The user identifier.
            limit: Maximum number of videos.

        Returns:
            ToolResult with mock user video data.
        """
        videos = [
            {
                "video_id": f"{user_id}_vid_001",
                "title": "最新作品 - 精彩内容",
                "likes": 3456,
                "comments": 123,
                "shares": 45,
                "duration": 90,
                "created_at": 1700000000000,
            },
            {
                "video_id": f"{user_id}_vid_002",
                "title": "热门视频 - 千万播放",
                "likes": 23456,
                "comments": 890,
                "shares": 567,
                "duration": 120,
                "created_at": 1699900000000,
            },
            {
                "video_id": f"{user_id}_vid_003",
                "title": "原创内容 - 独家分享",
                "likes": 1234,
                "comments": 56,
                "shares": 23,
                "duration": 60,
                "created_at": 1699800000000,
            },
        ]
        return ToolResult(
            success=True,
            data={
                "user_id": user_id,
                "videos": videos[:limit],
                "total": min(len(videos), limit),
                "source": "mock",
            },
        )

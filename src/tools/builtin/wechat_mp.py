from __future__ import annotations

import logging
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

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


class WeChatMpTool(ITool):
    """微信公众号文章数据工具 — requires official API key.

    本工具需要配置微信开放平台官方 API Key 才能使用。
    This tool requires WeChat Open Platform API Key.
    """

    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="wechat_mp",
            description=(
                "微信公众号数据工具（需配置官方 API Key）/ "
                "WeChat MP data tool (requires official API Key)"
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    required=True,
                    description=(
                        "操作类型 / Action: search_article, get_article, "
                        "get_account_articles"
                    ),
                ),
                ToolParameter(
                    name="params",
                    type="object",
                    required=True,
                    description="查询参数 / Query parameters (depends on action)",
                ),
            ],
        )

    async def execute(self, action: str, params: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=False,
            output=(
                "该功能需要配置微信开放平台官方 API Key。"
                "请设置 WECHAT_API_KEY 环境变量或将 "
                "_USE_OFFICIAL_API 设为 True。"
                " / This feature requires WeChat Open Platform "
                "API Key. Set WECHAT_API_KEY env var or "
                "_USE_OFFICIAL_API=True."
            ),
            error="Official API not configured",
        )

    def get_spec(self) -> ToolSpec:
        return self._spec
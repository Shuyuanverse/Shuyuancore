from __future__ import annotations

import logging
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

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


class WeiBoTool(ITool):
    """微博 public data tool — requires official API key.

    本工具需要配置微博开放平台官方 API Key 才能使用。
    This tool requires Weibo Open Platform API Key.
    """

    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="weibo",
            description=(
                "微博数据工具（需配置官方 API Key）/ "
                "Weibo data tool (requires official API Key)"
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    required=True,
                    description=(
                        "操作类型 / Action: search_weibo, get_weibo, "
                        "search_user, get_user_weibos, get_comments"
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

    async def execute(
        self, params: dict[str, Any], user_id: str = "default"
    ) -> ToolResult:
        action: str = params.get("action", "")
        if not action:
            return ToolResult(
                success=False,
                error="action parameter is required",
            )

        return ToolResult(
            success=False,
            data={"message": (
                "该功能需要配置微博开放平台官方 API Key。"
                "请设置 WEIBO_API_KEY 环境变量或将 "
                "_USE_OFFICIAL_API 设为 True。"
                " / This feature requires Weibo Open Platform "
                "API Key. Set WEIBO_API_KEY env var or "
                "_USE_OFFICIAL_API=True."
            )},
            error="Official API not configured",
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not params.get("action"):
            errors.append("action parameter is required")
        if not params.get("params"):
            errors.append("params parameter is required")
        return errors

    def get_spec(self) -> ToolSpec:
        return self._spec

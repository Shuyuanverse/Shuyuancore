from __future__ import annotations

import logging
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class XiaoHongShuTool(ITool):
    """小红书 public data tool — requires official API key.

    本工具需要配置小红书开放平台官方 API Key 才能使用。
    This tool requires Xiaohongshu Open Platform API Key.
    """

    _USE_OFFICIAL_API: bool = False

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="xiaohongshu",
            description=(
                "小红书数据工具（需配置官方 API Key）/ "
                "Xiaohongshu data tool (requires official API Key)"
            ),
            category="social",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    required=True,
                    description=(
                        "操作类型 / Action: search_notes, get_note, "
                        "search_users, get_comments"
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
                "该功能需要配置小红书开放平台官方 API Key。"
                "请设置 XIAOHONGSHU_API_KEY 环境变量或将 "
                "_USE_OFFICIAL_API 设为 True。"
                " / This feature requires Xiaohongshu Open Platform "
                "API Key. Set XIAOHONGSHU_API_KEY env var or "
                "_USE_OFFICIAL_API=True."
            ),
            error="Official API not configured",
        )

    def get_spec(self) -> ToolSpec:
        return self._spec
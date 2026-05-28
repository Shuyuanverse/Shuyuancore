from __future__ import annotations

import logging
import time
from typing import Any

from src.config import get_settings
from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, IToolRegistry, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class ToolRegistry(IToolRegistry):
    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        spec = tool.get_spec()
        self._tools[spec.name] = tool
        logger.info(
            "工具注册: %s（类别: %s, 危险: %s）",
            spec.name, spec.category, spec.dangerous,
        )

    def get_tool(self, name: str) -> ITool | None:
        return self._tools.get(name)

    def list_tools(self, category: str | None = None) -> list[ToolSpec]:
        if category is None:
            return [t.get_spec() for t in self._tools.values()]
        return [
            t.get_spec()
            for t in self._tools.values()
            if t.get_spec().category == category
        ]

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute_tool(
        self,
        name: str,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        start = time.time()
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"工具不存在: {name} / Tool not found: {name}",
            )

        spec = tool.get_spec()
        config = get_settings().tools

        validation_errors = await tool.validate(params)
        if validation_errors:
            return ToolResult(
                success=False,
                error="; ".join(validation_errors),
            )

        needs_approval = spec.dangerous
        approval_id = ""

        if needs_approval:
            approval_mgr = await get_approval_manager()
            req = await approval_mgr.request(
                tool_name=name,
                params=params,
                user_id=user_id,
                timeout=config.approval_timeout,
            )
            approval_id = req.approval_id
            approved = await approval_mgr.wait(
                approval_id, timeout=config.approval_timeout
            )
            if not approved:
                get_audit_logger().log(
                    user_id=user_id,
                    action="tool_execute",
                    resource=f"tool:{name}",
                    params=params,
                    result="denied",
                    approved=False,
                    approval_id=approval_id,
                    duration_ms=(time.time() - start) * 1000,
                )
                return ToolResult(
                    success=False,
                    error=f"工具操作被拒绝 / Tool operation denied ({approval_id})",
                    approval_id=approval_id,
                )

        try:
            result = await tool.execute(params=params, user_id=user_id)
            result.approval_id = approval_id
            duration = (time.time() - start) * 1000
            result.duration_ms = duration

            get_audit_logger().log(
                user_id=user_id,
                action="tool_execute",
                resource=f"tool:{name}",
                params=params,
                result="success" if result.success else "error",
                approved=True if needs_approval else None,
                approval_id=approval_id,
                duration_ms=duration,
                error=result.error if not result.success else "",
            )
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000
            get_audit_logger().log(
                user_id=user_id,
                action="tool_execute",
                resource=f"tool:{name}",
                params=params,
                result="error",
                approved=True if needs_approval else None,
                approval_id=approval_id,
                duration_ms=duration,
                error=str(e),
            )
            return ToolResult(
                success=False,
                error=f"工具执行异常: {e} / Tool execution error: {e}",
            )


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry

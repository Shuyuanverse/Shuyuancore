from __future__ import annotations

import time
import uuid
from typing import Any

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

_ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "delegate": {"task_description"},
    "check_status": {"task_id"},
    "cancel": {"task_id"},
}

_VALID_ACTIONS: frozenset[str] = frozenset({
    "delegate", "check_status", "cancel",
})


class DelegationTool(ITool):

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._spec = ToolSpec(
            name="delegation",
            description=(
                "子代理委托工具，支持创建子代理任务、"
                "检查任务状态和取消任务。"
            ),
            category="extension",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "操作类型：delegate（委托任务）/ "
                        "check_status（检查状态）/ cancel（取消任务）"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="task_description",
                    type="string",
                    description=(
                        "任务描述，delegate 操作必填"
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="task_id",
                    type="string",
                    description=(
                        "任务 ID，check_status 和 cancel 操作必填"
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="max_sub_agents",
                    type="integer",
                    description="最大子代理数量，默认为 3",
                    required=False,
                    default=3,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description=(
                        "任务超时时间（秒），默认为 300"
                    ),
                    required=False,
                    default=300,
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "").strip()

        if not action:
            errors.append("action is required and must not be empty")
            return errors

        if action not in _VALID_ACTIONS:
            valid = ", ".join(sorted(_VALID_ACTIONS))
            errors.append(
                f"Invalid action: {action}. Must be one of: {valid}"
            )
            return errors

        required = _ACTION_REQUIRED_PARAMS.get(action, set())
        for param in required:
            value = params.get(param)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(
                    f"'{param}' is required for action '{action}'"
                )

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        if action == "check_status":
            return await self._check_status(
                params, user_id, start, audit
            )

        from src.tools.approval import request_approval, wait_for_approval

        approval_req = await request_approval(
            tool_name="delegation",
            params=params,
            user_id=user_id,
        )
        approved = await wait_for_approval(approval_req.approval_id)
        if not approved:
            audit.log(
                user_id=user_id,
                action=f"delegation.{action}",
                resource="sub_agent",
                params=params,
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error=f"Delegation action '{action}' was not approved",
                approval_id=approval_req.approval_id,
                duration_ms=(time.time() - start) * 1000,
            )

        if action == "delegate":
            return await self._delegate_task(
                params, user_id, start, audit
            )
        elif action == "cancel":
            return await self._cancel_task(
                params, user_id, start, audit
            )

        return ToolResult(
            success=False,
            error=f"Unknown action: {action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _delegate_task(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        task_id = str(uuid.uuid4())
        max_sub_agents: int = params.get("max_sub_agents", 3)
        task_timeout: int = params.get("timeout", 300)

        task = {
            "task_id": task_id,
            "task_description": params["task_description"],
            "max_sub_agents": max_sub_agents,
            "timeout": task_timeout,
            "created_at": time.time(),
            "created_by": user_id,
            "status": "running",
            "sub_agents": [],
        }
        self._tasks[task_id] = task

        duration_ms = (time.time() - start) * 1000
        audit.log(
            user_id=user_id,
            action="delegation.delegate",
            resource=f"sub_agent:{task_id}",
            params={
                "task_description": task["task_description"],
                "max_sub_agents": max_sub_agents,
            },
            result="success",
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=True,
            data={
                "task_id": task_id,
                "status": "running",
                "task_description": task["task_description"],
            },
            duration_ms=duration_ms,
        )

    async def _check_status(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        task_id: str = params["task_id"]
        task = self._tasks.get(task_id)

        if task is None:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="delegation.check_status",
                resource=f"sub_agent:{task_id}",
                params=params,
                result="error",
                error="Task not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Task {task_id} not found",
                duration_ms=duration_ms,
            )

        duration_ms = (time.time() - start) * 1000
        audit.log(
            user_id=user_id,
            action="delegation.check_status",
            resource=f"sub_agent:{task_id}",
            params={"task_id": task_id},
            result="success",
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=True,
            data={
                "task_id": task_id,
                "status": task["status"],
                "task_description": task["task_description"],
                "created_at": task["created_at"],
                "sub_agents": task.get("sub_agents", []),
            },
            duration_ms=duration_ms,
        )

    async def _cancel_task(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        task_id: str = params["task_id"]
        task = self._tasks.get(task_id)

        if task is None:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="delegation.cancel",
                resource=f"sub_agent:{task_id}",
                params=params,
                result="error",
                error="Task not found",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Task {task_id} not found",
                duration_ms=duration_ms,
            )

        task["status"] = "cancelled"
        task["cancelled_at"] = time.time()

        duration_ms = (time.time() - start) * 1000
        audit.log(
            user_id=user_id,
            action="delegation.cancel",
            resource=f"sub_agent:{task_id}",
            params={"task_id": task_id},
            result="success",
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=True,
            data={
                "task_id": task_id,
                "status": "cancelled",
            },
            duration_ms=duration_ms,
        )

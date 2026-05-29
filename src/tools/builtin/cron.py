from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

_TASKS_FILE = Path("data/cron_tasks.json")

_ACTION_REQUIRED_PARAMS: dict[str, set[str]] = {
    "list": set(),
    "create": {"name", "cron_expression", "task_message"},
    "delete": {"task_id"},
    "trigger": {"task_id"},
}

_VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "list",
        "create",
        "delete",
        "trigger",
    }
)


class CronTool(ITool):
    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="cron",
            description=("定时任务管理工具，支持列出、创建、删除和立即触发定时任务。"),
            category="extension",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "操作类型：list（列出任务）/ create（创建任务）"
                        "/ delete（删除任务）/ trigger（立即触发）"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="任务名称，create 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="cron_expression",
                    type="string",
                    description=("Cron 表达式（5位），create 操作必填"),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="task_message",
                    type="string",
                    description="任务消息内容，create 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="task_id",
                    type="string",
                    description=("任务 ID，delete 和 trigger 操作必填"),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timezone",
                    type="string",
                    description="时区，默认为 Asia/Shanghai",
                    required=False,
                    default="Asia/Shanghai",
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="审批超时时间（秒）",
                    required=False,
                    default=30,
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
            errors.append(f"Invalid action: {action}. Must be one of: {valid}")
            return errors

        required = _ACTION_REQUIRED_PARAMS.get(action, set())
        for param in required:
            value = params.get(param)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"'{param}' is required for action '{action}'")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        if action == "list":
            return await self._list_tasks(user_id, start, audit)

        from src.tools.approval import request_approval, wait_for_approval

        approval_req = await request_approval(
            tool_name="cron",
            params=params,
            user_id=user_id,
        )
        approved = await wait_for_approval(approval_req.approval_id)
        if not approved:
            audit.log(
                user_id=user_id,
                action=f"cron.{action}",
                resource="cron_scheduler",
                params=params,
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error=f"Cron action '{action}' was not approved",
                approval_id=approval_req.approval_id,
                duration_ms=(time.time() - start) * 1000,
            )

        if action == "create":
            return await self._create_task(params, user_id, start, audit)
        elif action == "delete":
            return await self._delete_task(params, user_id, start, audit)
        elif action == "trigger":
            return await self._trigger_task(params, user_id, start, audit)

        return ToolResult(
            success=False,
            error=f"Unknown action: {action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _list_tasks(
        self,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        try:
            tasks = self._load_tasks()
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.list",
                resource="cron_scheduler",
                params={},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"tasks": tasks, "count": len(tasks)},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.list",
                resource="cron_scheduler",
                params={},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to list tasks: {e}",
                duration_ms=duration_ms,
            )

    async def _create_task(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        try:
            tasks = self._load_tasks()
            task_id = f"cron_{int(time.time())}_{len(tasks) + 1}"
            task = {
                "task_id": task_id,
                "name": params["name"],
                "cron_expression": params["cron_expression"],
                "task_message": params["task_message"],
                "timezone": params.get("timezone", "Asia/Shanghai"),
                "created_at": time.time(),
                "created_by": user_id,
                "status": "active",
            }
            tasks.append(task)
            self._save_tasks(tasks)

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.create",
                resource=f"cron_task:{task_id}",
                params={"name": task["name"]},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"task": task, "task_id": task_id},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.create",
                resource="cron_scheduler",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to create task: {e}",
                duration_ms=duration_ms,
            )

    async def _delete_task(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        task_id: str = params["task_id"]
        try:
            tasks = self._load_tasks()
            found = None
            for t in tasks:
                if t.get("task_id") == task_id:
                    found = t
                    break
            if found is None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="cron.delete",
                    resource=f"cron_task:{task_id}",
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

            tasks = [t for t in tasks if t.get("task_id") != task_id]
            self._save_tasks(tasks)

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.delete",
                resource=f"cron_task:{task_id}",
                params={"task_id": task_id},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"task_id": task_id, "status": "deleted"},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.delete",
                resource=f"cron_task:{task_id}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to delete task: {e}",
                duration_ms=duration_ms,
            )

    async def _trigger_task(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        task_id: str = params["task_id"]
        try:
            tasks = self._load_tasks()
            found = None
            for t in tasks:
                if t.get("task_id") == task_id:
                    found = t
                    break
            if found is None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="cron.trigger",
                    resource=f"cron_task:{task_id}",
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
                action="cron.trigger",
                resource=f"cron_task:{task_id}",
                params={"task_id": task_id, "name": found.get("name")},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "task_id": task_id,
                    "name": found.get("name"),
                    "task_message": found.get("task_message"),
                    "status": "triggered",
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="cron.trigger",
                resource=f"cron_task:{task_id}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to trigger task: {e}",
                duration_ms=duration_ms,
            )

    def _load_tasks(self) -> list[dict[str, Any]]:
        if not _TASKS_FILE.exists():
            _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            return []
        with open(_TASKS_FILE, encoding="utf-8") as f:
            return json.load(f)

    def _save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

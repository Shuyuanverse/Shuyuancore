from __future__ import annotations

import os
import signal
import time
from typing import Any

from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class ProcessTool(ITool):

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="process",
            description="进程管理工具，支持列出和终止进程。",
            category="system",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="操作类型：list（列出进程）或 kill（终止进程）",
                    required=True,
                ),
                ToolParameter(
                    name="pid",
                    type="integer",
                    description="进程 PID，kill 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="进程名称过滤关键字，仅 list 操作生效",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        operation = params.get("operation", "")
        if operation not in ("list", "kill"):
            errors.append("operation 必须是 list 或 kill")
        if operation == "kill":
            pid = params.get("pid")
            if pid is None:
                errors.append("kill 操作必须提供 pid 参数")
            elif not isinstance(pid, int) or pid <= 0:
                errors.append("pid 必须是正整数")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        operation: str = params["operation"]
        start = time.time()
        audit = get_audit_logger()

        if operation == "list":
            return await self._list_processes(params, user_id, start, audit)

        return await self._kill_process(params, user_id, start, audit)

    async def _list_processes(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name_filter: str | None = params.get("name")
        processes: list[dict[str, Any]] = []
        try:
            for entry in os.scandir("/proc"):
                if not entry.name.isdigit():
                    continue
                try:
                    pid = int(entry.name)
                    with open(f"/proc/{pid}/status") as f:
                        lines = f.readlines()
                    proc_name = ""
                    proc_status = ""
                    for line in lines:
                        if line.startswith("Name:"):
                            proc_name = line.split(":", 1)[1].strip()
                        elif line.startswith("State:"):
                            proc_status = line.split(":", 1)[1].strip()
                    if name_filter and name_filter not in proc_name:
                        continue
                    processes.append({
                        "pid": pid,
                        "name": proc_name,
                        "status": proc_status,
                    })
                except (OSError, IOError, ValueError):
                    continue
        except PermissionError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="process.list",
                resource="system",
                params=params,
                result="error",
                error="权限不足，无法读取 /proc",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error="权限不足，无法列出进程",
                duration_ms=duration_ms,
            )

        duration_ms = (time.time() - start) * 1000
        audit.log(
            user_id=user_id,
            action="process.list",
            resource="system",
            params=params,
            result="success",
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=True,
            data={"processes": processes, "count": len(processes)},
            duration_ms=duration_ms,
        )

    async def _kill_process(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        pid: int = params["pid"]

        try:
            os.kill(pid, 0)
        except OSError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="process.kill",
                resource=f"process:{pid}",
                params=params,
                result="error",
                error=f"进程 {pid} 不存在",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"进程 {pid} 不存在",
                duration_ms=duration_ms,
            )

        try:
            os.kill(pid, signal.SIGTERM)
        except PermissionError:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="process.kill",
                resource=f"process:{pid}",
                params=params,
                result="error",
                error=f"权限不足，无法终止进程 {pid}",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"权限不足，无法终止进程 {pid}",
                duration_ms=duration_ms,
            )
        except OSError as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="process.kill",
                resource=f"process:{pid}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"终止进程 {pid} 失败: {e}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.time() - start) * 1000
        audit.log(
            user_id=user_id,
            action="process.kill",
            resource=f"process:{pid}",
            params=params,
            result="success",
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=True,
            data={"pid": pid, "signal": "SIGTERM"},
            duration_ms=duration_ms,
        )

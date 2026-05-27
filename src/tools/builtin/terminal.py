from __future__ import annotations

import asyncio
import shlex
import time
from typing import Any

from src.config import get_settings
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec
from src.tools.sandbox import ToolSandbox


class TerminalTool(ITool):
    DANGEROUS_COMMANDS: frozenset[str] = frozenset(
        {
            "rm",
            "dd",
            "mkfs",
            "format",
            "shutdown",
            "reboot",
            "halt",
            "poweroff",
            ">",
            ">>",
            "|",
            "chmod",
            "chown",
        }
    )

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="terminal",
            description="执行终端命令。支持沙箱隔离执行，自动检测危险命令并触发审批流程。",
            category="system",
            dangerous=True,
            require_sandbox=True,
            require_approval=True,
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="要执行的终端命令",
                    required=True,
                ),
                ToolParameter(
                    name="cwd",
                    type="string",
                    description="命令执行的工作目录，默认为当前目录",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="env",
                    type="object",
                    description="命令执行时的额外环境变量",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="命令执行超时时间（秒）",
                    required=False,
                    default=60,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        command = params.get("command", "")
        if not command or not isinstance(command, str) or not command.strip():
            errors.append("command 参数不能为空")
        timeout = params.get("timeout", 60)
        if isinstance(timeout, int) and timeout < 1:
            errors.append("timeout 必须大于 0")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        command: str = params["command"]
        cwd: str | None = params.get("cwd")
        env: dict[str, str] | None = params.get("env")
        timeout: int = params.get("timeout", 60)

        start = time.time()
        audit = get_audit_logger()
        settings = get_settings()

        try:
            cmd_list = shlex.split(command)
        except ValueError as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="terminal.execute",
                resource="parse",
                params={"command": command},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"命令解析失败: {e}",
                duration_ms=duration_ms,
            )

        is_dangerous = self._contains_dangerous_command(command)

        sandbox = ToolSandbox(sandbox_mode=settings.tools.sandbox)
        sandbox_available = await sandbox.check_available()

        if not sandbox_available:
            if self._is_whitelisted(command, settings):
                local_result = await self._execute_local(
                    command=cmd_list,
                    cwd=cwd,
                    env=env,
                    timeout=timeout,
                )
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="terminal.execute",
                    resource="local_downgrade",
                    params={"command": command, "cwd": cwd, "timeout": timeout},
                    result="success" if local_result.success else "error",
                    approved=True,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=local_result.success,
                    data={
                        "stdout": (local_result.data or {}).get("stdout", ""),
                        "stderr": (local_result.data or {}).get("stderr", ""),
                        "exit_code": (local_result.data or {}).get("exit_code", -1),
                        "dangerous": is_dangerous,
                        "mode": "local",
                    },
                    error=local_result.error,
                    duration_ms=duration_ms,
                )

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="terminal.execute",
                resource="local",
                params={"command": command, "cwd": cwd, "timeout": timeout},
                result="approval_required",
                approved=None,
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error="沙箱不可用，在本地模式下执行非白名单命令需要审批",
                duration_ms=duration_ms,
                approval_id=user_id,
            )

        sandbox_result = await sandbox.execute_command(
            command=cmd_list,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

        duration_ms = (time.time() - start) * 1000

        if sandbox_result.success:
            audit.log(
                user_id=user_id,
                action="terminal.execute",
                resource="sandbox",
                params={
                    "command": command,
                    "cwd": cwd,
                    "timeout": timeout,
                    "dangerous": is_dangerous,
                },
                result="success",
                approved=True,
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "stdout": sandbox_result.stdout,
                    "stderr": sandbox_result.stderr,
                    "exit_code": sandbox_result.exit_code,
                    "dangerous": is_dangerous,
                },
                duration_ms=duration_ms,
            )

        audit.log(
            user_id=user_id,
            action="terminal.execute",
            resource="sandbox",
            params={
                "command": command,
                "cwd": cwd,
                "timeout": timeout,
                "dangerous": is_dangerous,
            },
            result="error",
            error=sandbox_result.error or sandbox_result.stderr,
            duration_ms=duration_ms,
        )
        return ToolResult(
            success=False,
            data={
                "stdout": sandbox_result.stdout,
                "stderr": sandbox_result.stderr,
                "exit_code": sandbox_result.exit_code,
                "dangerous": is_dangerous,
            },
            error=sandbox_result.error or sandbox_result.stderr,
            duration_ms=duration_ms,
        )

    def _contains_dangerous_command(self, command: str) -> bool:
        tokens = shlex.split(command)
        for token in tokens:
            if token in self.DANGEROUS_COMMANDS:
                return True
        return False

    def _is_whitelisted(self, command: str, settings: Any) -> bool:
        base_cmd = shlex.split(command)[0] if shlex.split(command) else ""
        whitelist = settings.tools.terminal_whitelist
        return base_cmd in whitelist

    async def _execute_local(
        self,
        command: list[str],
        cwd: str | None,
        env: dict[str, str] | None,
        timeout: int,
    ) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode or 0
            return ToolResult(
                success=exit_code == 0,
                data={
                    "stdout": stdout.decode(errors="replace"),
                    "stderr": stderr.decode(errors="replace"),
                    "exit_code": exit_code,
                    "mode": "local",
                },
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(
                success=False,
                error=f"命令执行超时（{timeout}秒）",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

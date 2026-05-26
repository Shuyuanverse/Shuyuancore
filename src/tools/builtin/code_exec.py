from __future__ import annotations

import time
from typing import Any

from src.config import get_settings
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec
from src.tools.sandbox import ToolSandbox

SUPPORTED_LANGUAGES = frozenset({"python", "javascript"})


class CodeExecTool(ITool):

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="code_exec",
            description="在沙箱环境中执行代码。支持 Python 和 JavaScript，强制在 Docker 沙箱中运行。",
            category="system",
            dangerous=True,
            require_sandbox=True,
            require_approval=True,
            parameters=[
                ToolParameter(
                    name="code",
                    type="string",
                    description="要执行的代码内容",
                    required=True,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="代码语言，支持 python/javascript",
                    required=False,
                    default="python",
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="代码执行超时时间（秒）",
                    required=False,
                    default=30,
                ),
                ToolParameter(
                    name="memory_limit",
                    type="string",
                    description="内存限制，如 256m、512m",
                    required=False,
                    default="256m",
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        code = params.get("code", "")
        if not code or not isinstance(code, str) or not code.strip():
            errors.append("code 参数不能为空")
        language = params.get("language", "python")
        if language not in SUPPORTED_LANGUAGES:
            errors.append(f"不支持的语言: {language}，仅支持 {', '.join(sorted(SUPPORTED_LANGUAGES))}")
        timeout = params.get("timeout", 30)
        if isinstance(timeout, int) and timeout < 1:
            errors.append("timeout 必须大于 0")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        code: str = params["code"]
        language: str = params.get("language", "python")
        timeout: int = params.get("timeout", 30)
        memory_limit: str = params.get("memory_limit", "256m")

        start = time.time()
        audit = get_audit_logger()
        settings = get_settings()

        sandbox = ToolSandbox(sandbox_mode=settings.tools.sandbox)
        sandbox_available = await sandbox.check_available()

        if not sandbox_available:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="code_exec.execute",
                resource="sandbox",
                params={
                    "language": language,
                    "timeout": timeout,
                    "memory_limit": memory_limit,
                },
                result="error",
                error="Docker 沙箱不可用，代码执行需要沙箱环境",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error="Docker 沙箱不可用，代码执行必须在沙箱环境中运行",
                duration_ms=duration_ms,
            )

        sandbox_result = await sandbox.execute_code(
            code=code,
            language=language,
            timeout=timeout,
            memory_limit=memory_limit,
        )

        duration_ms = (time.time() - start) * 1000

        if sandbox_result.success:
            audit.log(
                user_id=user_id,
                action="code_exec.execute",
                resource="sandbox",
                params={
                    "language": language,
                    "timeout": timeout,
                    "memory_limit": memory_limit,
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
                },
                duration_ms=duration_ms,
            )

        audit.log(
            user_id=user_id,
            action="code_exec.execute",
            resource="sandbox",
            params={
                "language": language,
                "timeout": timeout,
                "memory_limit": memory_limit,
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
            },
            error=sandbox_result.error or sandbox_result.stderr,
            duration_ms=duration_ms,
        )
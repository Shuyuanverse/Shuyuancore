from __future__ import annotations

from src.security.sandbox import SandboxExecutor, SandboxResult


class ToolSandbox:
    def __init__(self, sandbox_mode: str = "docker"):
        self._executor = SandboxExecutor(sandbox_mode)

    async def execute_command(
        self,
        command: list[str],
        timeout: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxResult:
        return await self._executor.execute(
            command=command,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        memory_limit: str = "256m",
    ) -> SandboxResult:
        if language == "python":
            cmd = ["python3", "-c", code]
        elif language == "javascript":
            cmd = ["node", "-e", code]
        else:
            return SandboxResult(
                success=False,
                error=f"不支持的语言: {language} / Unsupported language: {language}",
                exit_code=-1,
            )
        return await self._executor.execute(
            command=cmd,
            timeout=timeout,
            memory_limit=memory_limit,
        )

    async def check_available(self) -> bool:
        return await self._executor.check_docker()

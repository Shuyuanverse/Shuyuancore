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
        return await self._executor.execute(
            command=["python3", "-"] if language == "python" else (
                ["node", "-"] if language == "javascript" else [""]
            ),
            timeout=timeout,
            memory_limit=memory_limit,
            stdin_data=code,
        )

    async def check_available(self) -> bool:
        return await self._executor.check_docker()

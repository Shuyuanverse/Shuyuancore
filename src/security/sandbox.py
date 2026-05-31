from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class SandboxResult:
    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        error: str = "",
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "error": self.error,
        }


class SandboxExecutor:
    def __init__(self, sandbox_mode: str = "docker"):
        self._sandbox_mode = sandbox_mode
        self._docker_available: bool | None = None
        self._last_check_time: float = 0.0
        self._cache_ttl: float = 60.0

    async def check_docker(self) -> bool:
        now = time.time()
        if self._docker_available is not None and (now - self._last_check_time) < self._cache_ttl:
            return self._docker_available
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            self._docker_available = proc.returncode == 0
            self._last_check_time = time.time()
            if not self._docker_available:
                logger.warning("Docker 不可用: %s", stderr.decode())
            return self._docker_available
        except FileNotFoundError:
            self._docker_available = False
            self._last_check_time = time.time()
            logger.warning("docker 命令未找到，Docker 沙箱不可用")
            return False

    async def execute(
        self,
        command: list[str],
        timeout: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        memory_limit: str = "256m",
        image: str = "ubuntu:22.04",
    ) -> SandboxResult:
        if self._sandbox_mode == "docker" and await self.check_docker():
            return await self._execute_docker(command, timeout, env, memory_limit, image)
        return await self._execute_local(command, timeout, env, cwd)

    async def _execute_docker(
        self,
        command: list[str],
        timeout: int = 60,
        env: dict[str, str] | None = None,
        memory_limit: str = "256m",
        image: str = "ubuntu:22.04",
    ) -> SandboxResult:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--memory",
            memory_limit,
            "--network",
            "none",
            "--read-only",
        ]
        if env:
            for key, value in env.items():
                cmd.extend(["-e", f"{key}={value}"])
        cmd.append(image)
        cmd.extend(command)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            success = proc.returncode == 0
            return SandboxResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"命令执行超时（{timeout}s） / Command timeout ({timeout}s)",
                exit_code=-1,
            )
        except FileNotFoundError as e:
            return SandboxResult(
                success=False,
                error=f"Docker 执行失败: {e}",
                exit_code=-1,
            )

    async def _execute_local(
        self,
        command: list[str],
        timeout: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxResult:
        env_full = os.environ.copy()
        if env:
            env_full.update(env)
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_full,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            success = proc.returncode == 0
            return SandboxResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"命令执行超时（{timeout}s） / Command timeout ({timeout}s)",
                exit_code=-1,
            )
        except FileNotFoundError as e:
            return SandboxResult(
                success=False,
                error=f"命令未找到: {e} / Command not found: {e}",
                exit_code=-1,
            )

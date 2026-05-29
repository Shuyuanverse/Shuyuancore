from __future__ import annotations

import subprocess
import time
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

try:
    import httpx

    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class MonitoringTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="monitoring",
            description="Server monitoring and website availability check tool. "
            "Supports server_status, website_check, and ping operations.",
            category="extension",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Operation: server_status / website_check / ping",
                    required=True,
                ),
                ToolParameter(
                    name="url",
                    type="string",
                    description="Target URL, required for website_check",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="host",
                    type="string",
                    description="Target host, required for ping",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "")
        valid_actions = {"server_status", "website_check", "ping"}
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors
        if action == "website_check" and not params.get("url"):
            errors.append("website_check operation requires url parameter")
        if action == "ping" and not params.get("host"):
            errors.append("ping operation requires host parameter")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()

        if action == "server_status":
            return await self._server_status(start)
        elif action == "website_check":
            return await self._website_check(
                params.get("url", ""),
                int(params.get("timeout", 30)),
                start,
            )
        else:
            return await self._ping(
                params.get("host", ""),
                int(params.get("timeout", 30)),
                start,
            )

    async def _server_status(self, start: float) -> ToolResult:
        if not _HAS_PSUTIL:
            return ToolResult(
                success=False,
                error="psutil is not installed. Install it with: pip install psutil",
                duration_ms=(time.time() - start) * 1000,
            )
        try:
            cpu_percent: float = psutil.cpu_percent(interval=1.0)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            data = {
                "cpu": {
                    "percent": cpu_percent,
                    "cores": psutil.cpu_count(),
                    "logical_cores": psutil.cpu_count(logical=True),
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                },
            }
            return ToolResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error=f"Failed to get server status: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _website_check(
        self,
        url: str,
        timeout: int,
        start: float,
    ) -> ToolResult:
        if not _HAS_HTTPX:
            return ToolResult(
                success=False,
                error="httpx is not installed. Install it with: pip install httpx",
                duration_ms=(time.time() - start) * 1000,
            )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                request_start = time.time()
                response = await client.get(url)
                response_time = (time.time() - request_start) * 1000
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "status_code": response.status_code,
                        "response_time_ms": round(response_time, 2),
                        "accessible": response.status_code < 500,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )
        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Request to {url} timed out after {timeout}s",
                duration_ms=(time.time() - start) * 1000,
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to check website {url}: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _ping(
        self,
        host: str,
        timeout: int,
        start: float,
    ) -> ToolResult:
        try:
            ping_start = time.time()
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout), host],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            response_time = (time.time() - ping_start) * 1000
            success = result.returncode == 0
            return ToolResult(
                success=True,
                data={
                    "host": host,
                    "reachable": success,
                    "response_time_ms": round(response_time, 2),
                    "output": result.stdout.strip() if success else result.stderr.strip(),
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Ping to {host} timed out",
                duration_ms=(time.time() - start) * 1000,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="ping command not found on this system",
                duration_ms=(time.time() - start) * 1000,
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error=f"Failed to ping {host}: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

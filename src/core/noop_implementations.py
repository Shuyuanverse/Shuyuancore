from __future__ import annotations

import json
import time
from typing import Any

from src.core.interfaces import (
    IMemoryStore,
    IPersonaGuard,
    ISkillEngine,
    IToolRegistry,
    ToolSpec,
)


class NoOpMemoryStore(IMemoryStore):
    pass


class NoOpPersonaGuard(IPersonaGuard):
    pass


class NoOpSkillEngine(ISkillEngine):
    pass


class MockToolRegistry(IToolRegistry):

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {
            "echo": ToolSpec(
                name="echo",
                description="Echo back the input text",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to echo",
                        }
                    },
                    "required": ["text"],
                },
            ),
            "get_current_time": ToolSpec(
                name="get_current_time",
                description="Get the current system time",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        }

    async def execute(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        if tool_name == "echo":
            text = arguments.get("text", "")
            return f"echo: {text}"
        if tool_name == "get_current_time":
            return json.dumps(
                {
                    "time": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime()
                    ),
                    "timestamp_ms": int(time.time() * 1000),
                }
            )
        return f"unknown tool: {tool_name}"

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> ToolSpec | None:
        return self._tools.get(tool_name)

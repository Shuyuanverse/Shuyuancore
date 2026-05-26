from __future__ import annotations

import json
import time
from typing import Any

from src.core.interfaces import (
    Belief,
    IBeliefStore,
    IMemoryStore,
    IPersonaGuard,
    ISkillEngine,
    IToolRegistry,
    ToolSpec,
)


class NoOpBeliefStore(IBeliefStore):

    async def add(self, conversation_id: str, belief: Belief) -> str:
        return belief.id

    async def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        return []

    async def get_by_id(self, belief_id: str) -> Belief | None:
        return None

    async def update(self, belief: Belief) -> None:
        pass

    async def clear(self, conversation_id: str) -> None:
        pass

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        pass

    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]:
        return []

    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None:
        pass

    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        pass


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

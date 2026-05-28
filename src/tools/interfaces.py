from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str
    parameters: list[ToolParameter] = field(default_factory=list)
    dangerous: bool = False
    require_sandbox: bool = False
    require_approval: bool = False


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    approval_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "approval_id": self.approval_id,
        }


class ITool(ABC):

    @abstractmethod
    def get_spec(self) -> ToolSpec:
        ...

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        ...

    @abstractmethod
    async def validate(self, params: dict[str, Any]) -> list[str]:
        ...


class IToolRegistry(ABC):

    @abstractmethod
    def register(self, tool: ITool) -> None:
        ...

    @abstractmethod
    def get_tool(self, name: str) -> ITool | None:
        ...

    @abstractmethod
    def list_tools(self, category: str | None = None) -> list[ToolSpec]:
        ...

    @abstractmethod
    async def execute_tool(
        self,
        name: str,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        ...

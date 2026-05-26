from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Belief:
    id: str
    content: str
    source: str  # user | assistant | tool | system
    confidence: float = 1.0
    timestamp: int = 0
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class IBeliefStore(ABC):

    @abstractmethod
    def add(self, conversation_id: str, belief: Belief) -> None:
        ...

    @abstractmethod
    def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        ...

    @abstractmethod
    def clear(self, conversation_id: str) -> None:
        ...

    @abstractmethod
    def remove(self, conversation_id: str, belief_id: str) -> None:
        ...


class IReader(ABC):

    @abstractmethod
    def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        ...


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


class IToolRegistry(ABC):

    @abstractmethod
    async def execute(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        ...

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        ...

    @abstractmethod
    def get_tool(self, tool_name: str) -> ToolSpec | None:
        ...


class IMemoryStore(ABC):
    pass


class IPersonaGuard(ABC):
    pass


class ISkillEngine(ABC):
    pass

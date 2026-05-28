from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Belief:
    id: str
    content: str
    source: str
    confidence: float = 1.0
    base_confidence: float = 1.0
    last_accessed: int = 0
    memory_type: str = "chat"
    layer: int = 3
    entities: list[str] = field(default_factory=list)
    emotion: float = 0.5
    depends_on: list[str] = field(default_factory=list)
    child_belief_ids: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    status: str = "active"
    is_composite: bool = False
    timestamp: int = 0
    conversation_date: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


MEMORY_TYPE_LAYER_MAP: dict[str, int] = {
    "identity": 1,
    "preference": 1,
    "fact": 3,
    "task": 2,
    "agreement": 2,
    "emotion": 5,
    "chat": 3,
}


class IBeliefStore(ABC):

    @abstractmethod
    async def add(self, conversation_id: str, belief: Belief) -> str:
        ...

    @abstractmethod
    async def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        ...

    @abstractmethod
    async def get_by_id(self, belief_id: str) -> Belief | None:
        ...

    @abstractmethod
    async def update(self, belief: Belief) -> None:
        ...

    @abstractmethod
    async def clear(self, conversation_id: str) -> None:
        ...

    @abstractmethod
    async def remove(self, conversation_id: str, belief_id: str) -> None:
        ...

    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]:
        ...

    @abstractmethod
    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None:
        ...

    @abstractmethod
    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        ...


class IReader(ABC):

    @abstractmethod
    async def read(
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

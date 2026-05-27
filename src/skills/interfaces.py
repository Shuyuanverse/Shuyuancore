from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ISkillStore(ABC):

    @abstractmethod
    async def list_skills(
        self, status: str = "active", source: str | None = None
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def get_skill(self, name: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    async def create_skill(
        self,
        node: dict[str, Any],
        conversation_id: str,
    ) -> str:
        ...

    @abstractmethod
    async def update_skill(self, node: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def delete_skill(self, name: str) -> None:
        ...


class ISkillGraph(ABC):

    @abstractmethod
    async def add_edge(self, edge: dict[str, Any]) -> str:
        ...

    @abstractmethod
    async def get_edges(
        self, node_name: str | None = None
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def remove_edge(self, edge_id: str) -> None:
        ...

    @abstractmethod
    async def traverse(
        self, start_name: str
    ) -> list[dict[str, Any]]:
        ...

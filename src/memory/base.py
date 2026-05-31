# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    id: str
    content: str
    memory_type: str = "general"
    layer: int = 3
    confidence: float = 1.0
    created_at: int = 0
    last_accessed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryStats:
    total_entries: int = 0
    by_layer: dict[int, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    total_size_bytes: int = 0
    oldest_entry: int = 0
    newest_entry: int = 0


class MemoryBase(ABC):
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        raise NotImplementedError

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        raise NotImplementedError

    @abstractmethod
    async def update(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entry_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear(self) -> None:
        raise NotImplementedError
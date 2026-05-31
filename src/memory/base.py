# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""记忆系统基础定义 — 抽象基类与数据类。

使用指引：
- MemoryBase：所有记忆存储后端的抽象基类
- MemoryEntry：记忆条目数据类，包含 id/content/memory_type/layer 等字段
- MemoryStats：统计信息数据类

具体实现参见 LongTermMemory (long_term.py)、VectorStore (vector_store.py)、
PersistentBeliefStore (belief_store.py)。
"""

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
        raise NotImplementedError("Subclasses must implement store()")

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        raise NotImplementedError("Subclasses must implement retrieve()")

    @abstractmethod
    async def update(self, entry: MemoryEntry) -> None:
        raise NotImplementedError("Subclasses must implement update()")

    @abstractmethod
    async def delete(self, entry_id: str) -> None:
        raise NotImplementedError("Subclasses must implement delete()")

    @abstractmethod
    async def clear(self) -> None:
        raise NotImplementedError("Subclasses must implement clear()")
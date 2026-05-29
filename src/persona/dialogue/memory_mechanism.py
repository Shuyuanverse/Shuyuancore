# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""三层记忆机制 — 短期 + 长期 + 核心。

MemoryMechanism 管理三层记忆：
- SHORT_TERM: 会话级，TTL=300 秒，最多 100 条
- LONG_TERM: 跨会话，访问>=3 次晋升
- CORE: 持久化，访问>=10 次晋升

store(key, value, memory_type, importance) → MemoryEntry
recall(query, memory_type, top_k) → RecallResult
consolidate() → Dict  # 整合：清理过期 + 晋升
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import numpy as np

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""

    SHORT_TERM = "short_term"  # 短期记忆
    LONG_TERM = "long_term"  # 长期记忆
    CORE = "core"  # 核心记忆


@dataclass
class MemoryEntry:
    """记忆条目

    Attributes:
        key: 键
        value: 值
        memory_type: 记忆类型
        importance: 重要性 0-1
        access_count: 访问次数
        last_access: 最后访问时间
        expires_at: 过期时间
        tags: 标签列表
        embedding: 嵌入向量（可选）
    """

    key: str
    value: Any
    memory_type: MemoryType
    importance: float = 0.5
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    embedding: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "key": self.key,
            "value": self.value,
            "memory_type": self.memory_type.value,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_access": self.last_access,
            "expires_at": self.expires_at,
            "tags": self.tags,
            "has_embedding": self.embedding is not None,
        }

    def touch(self) -> None:
        """更新访问时间"""
        self.access_count += 1
        self.last_access = time.time()


@dataclass
class RecallResult:
    """记忆召回结果

    Attributes:
        entries: 召回的记忆条目
        scores: 相似度分数
        total_retrieved: 召回总数
    """

    entries: List[MemoryEntry]
    scores: List[float]
    total_retrieved: int

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "entries": [e.to_dict() for e in self.entries],
            "scores": self.scores,
            "total_retrieved": self.total_retrieved,
        }


class MemoryMechanism:
    """三层记忆机制

    - SHORT_TERM: 会话级，TTL=300 秒，最多 100 条
    - LONG_TERM: 跨会话，访问>=3 次晋升
    - CORE: 持久化，访问>=10 次晋升

    store(key, value, memory_type, importance) → MemoryEntry
    recall(query, memory_type, top_k) → RecallResult
    consolidate() → Dict  # 整合：清理过期 + 晋升
    """

    def __init__(self):
        """初始化记忆机制"""
        # 三层记忆存储
        self._short_term: Dict[str, MemoryEntry] = {}
        self._long_term: Dict[str, MemoryEntry] = {}
        self._core: Dict[str, MemoryEntry] = {}

        # 配置
        self._short_term_ttl = 300  # 5 分钟
        self._short_term_max = 100
        self._long_term_promotion_threshold = 3
        self._core_promotion_threshold = 10

        logger.info(
            "[memory] 记忆机制初始化完成，short_term_ttl=%ds, max=%d",
            self._short_term_ttl,
            self._short_term_max,
        )

    def store(
        self,
        key: str,
        value: Any,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        embedding: Optional[np.ndarray] = None,
    ) -> MemoryEntry:
        """存储记忆

        Args:
            key: 键
            value: 值
            memory_type: 记忆类型
            importance: 重要性
            tags: 标签
            embedding: 嵌入向量

        Returns:
            MemoryEntry: 记忆条目
        """
        # 设置过期时间（仅短期记忆）
        expires_at = None
        if memory_type == MemoryType.SHORT_TERM:
            expires_at = time.time() + self._short_term_ttl

        # 创建记忆条目
        entry = MemoryEntry(
            key=key,
            value=value,
            memory_type=memory_type,
            importance=importance,
            tags=tags or [],
            embedding=embedding,
            expires_at=expires_at,
        )

        # 存储到对应层
        if memory_type == MemoryType.SHORT_TERM:
            self._short_term[key] = entry

            # 检查是否超出容量
            if len(self._short_term) > self._short_term_max:
                self._evict_short_term()

        elif memory_type == MemoryType.LONG_TERM:
            self._long_term[key] = entry

        elif memory_type == MemoryType.CORE:
            self._core[key] = entry

        logger.debug(
            "[memory] 存储记忆：key=%s, type=%s, importance=%.2f",
            key,
            memory_type.value,
            importance,
        )

        return entry

    def recall(
        self,
        query: str,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        top_k: int = 5,
    ) -> RecallResult:
        """召回记忆

        Args:
            query: 查询
            memory_type: 记忆类型
            top_k: 召回数量

        Returns:
            RecallResult: 召回结果
        """
        # 选择记忆库
        if memory_type == MemoryType.SHORT_TERM:
            memory_store = self._short_term
        elif memory_type == MemoryType.LONG_TERM:
            memory_store = self._long_term
        elif memory_type == MemoryType.CORE:
            memory_store = self._core
        else:
            memory_store = self._short_term

        if not memory_store:
            return RecallResult(entries=[], scores=[], total_retrieved=0)

        # 简化实现：基于关键词匹配
        # TODO: 实现真实的向量相似度检索

        query_words = set(query.lower().split())

        scored_entries = []

        for key, entry in memory_store.items():
            # 检查过期
            if entry.expires_at and time.time() > entry.expires_at:
                continue

            # 计算相似度（简化：关键词重叠）
            key_words = set(key.lower().split())
            overlap = len(query_words & key_words)
            score = overlap / max(len(query_words | key_words), 1)

            # 考虑重要性
            score *= entry.importance

            # 考虑访问次数
            score *= 1 + entry.access_count * 0.1

            scored_entries.append((entry, score))

        # 按分数排序
        scored_entries.sort(key=lambda x: x[1], reverse=True)

        # 取 top_k
        top_entries = [e for e, _ in scored_entries[:top_k]]
        top_scores = [s for _, s in scored_entries[:top_k]]

        # 更新访问记录
        for entry in top_entries:
            entry.touch()

        result = RecallResult(
            entries=top_entries,
            scores=top_scores,
            total_retrieved=len(top_entries),
        )

        logger.debug(
            "[memory] 召回记忆：type=%s, query=%s, retrieved=%d",
            memory_type.value,
            query[:20],
            result.total_retrieved,
        )

        return result

    def consolidate(self) -> Dict[str, Any]:
        """整合记忆：清理过期 + 晋升

        Returns:
            Dict: 整合报告
        """
        report = {
            "expired_removed": 0,
            "promoted_to_long_term": 0,
            "promoted_to_core": 0,
            "demoted_to_long_term": 0,
        }

        current_time = time.time()

        # Step 1: 清理短期记忆中的过期条目
        expired_keys = [
            key
            for key, entry in self._short_term.items()
            if entry.expires_at and current_time > entry.expires_at
        ]

        for key in expired_keys:
            del self._short_term[key]
            report["expired_removed"] += 1

        # Step 2: 晋升短期记忆到长期记忆（访问>=3 次）
        promote_to_long_term = [
            key
            for key, entry in self._short_term.items()
            if entry.access_count >= self._long_term_promotion_threshold
        ]

        for key in promote_to_long_term:
            entry = self._short_term.pop(key)
            entry.memory_type = MemoryType.LONG_TERM
            entry.expires_at = None  # 长期记忆不过期
            self._long_term[key] = entry
            report["promoted_to_long_term"] += 1

        # Step 3: 晋升长期记忆到核心记忆（访问>=10 次）
        promote_to_core = [
            key
            for key, entry in self._long_term.items()
            if entry.access_count >= self._core_promotion_threshold
        ]

        for key in promote_to_core:
            entry = self._long_term.pop(key)
            entry.memory_type = MemoryType.CORE
            self._core[key] = entry
            report["promoted_to_core"] += 1

        logger.info(
            "[memory] 整合完成：expired=%d, promoted_lt=%d, promoted_core=%d",
            report["expired_removed"],
            report["promoted_to_long_term"],
            report["promoted_to_core"],
        )

        return report

    def _evict_short_term(self) -> None:
        """驱逐短期记忆（LRU 策略）"""
        if len(self._short_term) <= self._short_term_max:
            return

        # 按最后访问时间排序
        sorted_entries = sorted(
            self._short_term.items(),
            key=lambda x: x[1].last_access,
        )

        # 驱逐最旧的
        evict_count = len(self._short_term) - self._short_term_max
        for i in range(evict_count):
            key, _ = sorted_entries[i]
            del self._short_term[key]

        logger.debug("[memory] 驱逐短期记忆：%d 条", evict_count)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
            "core_count": len(self._core),
            "total_count": len(self._short_term) + len(self._long_term) + len(self._core),
        }

    def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        """清空记忆

        Args:
            memory_type: 记忆类型（None 则清空所有）
        """
        if memory_type is None:
            self._short_term.clear()
            self._long_term.clear()
            self._core.clear()
            logger.info("[memory] 清空所有记忆")
        elif memory_type == MemoryType.SHORT_TERM:
            self._short_term.clear()
            logger.info("[memory] 清空短期记忆")
        elif memory_type == MemoryType.LONG_TERM:
            self._long_term.clear()
            logger.info("[memory] 清空长期记忆")
        elif memory_type == MemoryType.CORE:
            self._core.clear()
            logger.info("[memory] 清空核心记忆")

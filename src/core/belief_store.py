"""内存版 BeliefStore — 轻量实现，适用于测试和小规模场景。

注意：生产环境请使用 src.memory.belief_store.PersistentBeliefStore（SQLite 持久化版）。
此实现适合测试和开发，search_similar 使用简单关键词匹配而非向量嵌入。
"""

from __future__ import annotations

from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms


class BeliefStore(IBeliefStore):
    def __init__(self) -> None:
        self._store: dict[str, list[Belief]] = {}
        self._by_id: dict[str, Belief] = {}

    async def add(self, conversation_id: str, belief: Belief) -> str:
        if conversation_id not in self._store:
            self._store[conversation_id] = []
        self._store[conversation_id].append(belief)
        self._by_id[belief.id] = belief
        return belief.id

    async def get(self, conversation_id: str, limit: int = 50) -> list[Belief]:
        beliefs = self._store.get(conversation_id, [])
        return beliefs[-limit:]

    async def get_by_id(self, belief_id: str) -> Belief | None:
        return self._by_id.get(belief_id)

    async def update(self, belief: Belief) -> None:
        self._by_id[belief.id] = belief

    async def clear(self, conversation_id: str) -> None:
        beliefs = self._store.pop(conversation_id, [])
        for b in beliefs:
            self._by_id.pop(b.id, None)

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        beliefs = self._store.get(conversation_id)
        if beliefs is None:
            return
        self._store[conversation_id] = [b for b in beliefs if b.id != belief_id]
        self._by_id.pop(belief_id, None)

    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]:
        """使用关键词匹配搜索相似信念（内存版轻量实现）。

        Args:
            query: 查询文本
            top_k: 返回结果数量上限
            min_confidence: 最低置信度阈值

        Returns:
            list[tuple[Belief, float]]: (信念, 相似度) 列表
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        scored: list[tuple[Belief, float]] = []
        for belief in self._by_id.values():
            if belief.confidence < min_confidence:
                continue
            if belief.status != "active":
                continue

            content_lower = belief.content.lower()
            content_tokens = set(content_lower.split())
            if not query_tokens or not content_tokens:
                continue
            intersection = query_tokens & content_tokens
            union = query_tokens | content_tokens
            similarity = len(intersection) / len(union)

            if similarity > 0:
                scored.append((belief, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def get_similar_task_count(
        self,
        query: str,
        days: int = 7,
        similarity_threshold: float = 0.8,
    ) -> int:
        """统计与给定查询相似的信念数量（内存版）。

        Args:
            query: 查询文本
            days: 天数窗口（内存版忽略时间过滤）
            similarity_threshold: 相似度阈值

        Returns:
            int: 相似信念数量
        """
        similar = await self.search_similar(query, top_k=100, min_confidence=0.1)
        cutoff = current_time_ms() - days * 24 * 60 * 60 * 1000
        count = sum(
            1 for _, score in similar
            if score >= similarity_threshold
        )
        return count

    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None:
        """递归传播置信度变化到依赖信念。

        Args:
            belief_id: 信念 ID
            delta: 置信度变化量
            visited: 已访问集合，用于防环
        """
        if visited is None:
            visited = set()
        if belief_id in visited:
            return
        visited.add(belief_id)

        belief = self._by_id.get(belief_id)
        if belief is None:
            return

        belief.confidence = max(0.0, min(1.0, belief.confidence + delta))

        for dep_id in belief.depends_on:
            decayed = delta * 0.5
            if abs(decayed) > 0.01:
                await self.propagate_confidence(dep_id, decayed, visited)

    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        """推翻旧信念，用新信念替代。

        Args:
            old_id: 旧信念 ID
            new_id: 新信念 ID
            reason: 推翻原因
        """
        old = self._by_id.get(old_id)
        if old is None:
            return

        old.status = "superseded"
        old.superseded_by = new_id
        if old.metadata is None:
            old.metadata = {}
        old.metadata["overthrow_reason"] = reason

        new = self._by_id.get(new_id)
        if new is not None:
            new.depends_on = [d for d in new.depends_on if d != old_id]

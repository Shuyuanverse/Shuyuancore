"""基于 BeliefStore 的分层读取器 — 支持按层优先级和查询相关性排序。

职责区分：
- BeliefReader：从 IBeliefStore 读取 belief，按 layer 分层（L1 > L2 > 查询匹配 > 其余）
- 与 src/core/reader.py 的 Reader 不同，这里实现分层优先级检索
- Reader 是简单的时间逆序组装，适用于简单场景
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.interfaces import Belief, IBeliefStore, IReader
from src.core.reader import get_real_callable_attr

logger = logging.getLogger(__name__)

_MEMORY_TYPE_ROLE_MAP: dict[str, str] = {
    "identity": "system",
    "preference": "system",
    "task": "system",
    "agreement": "system",
    "fact": "system",
    "emotion": "system",
    "chat": "assistant",
}


class BeliefReader(IReader):
    def __init__(self, belief_store: IBeliefStore) -> None:
        self._belief_store = belief_store

    async def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]:
        if user_query:
            ebl_messages = await self._read_evidence_belief_context(
                conversation_id=conversation_id,
                user_query=user_query,
                max_tokens=max_tokens,
            )
            if ebl_messages:
                return ebl_messages

        all_beliefs = await self._belief_store.get(conversation_id, limit=200)

        l1_beliefs: list[Belief] = []
        l2_beliefs: list[Belief] = []
        l3_plus_beliefs: list[Belief] = []

        for belief in all_beliefs:
            if belief.layer == 1:
                l1_beliefs.append(belief)
            elif belief.layer == 2:
                l2_beliefs.append(belief)
            else:
                l3_plus_beliefs.append(belief)

        similar_beliefs: list[tuple[Belief, float]] = []
        if user_query:
            similar_beliefs = await self._belief_store.search_similar(
                user_query, top_k=5, min_confidence=0.1
            )

        seen_ids: set[str] = set()
        scored_beliefs: list[tuple[Belief, float]] = []

        for belief in l1_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 1.0
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        for belief in l2_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 0.9
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        if similar_beliefs:
            for belief, relevance in similar_beliefs:
                if belief.id not in seen_ids:
                    score = belief.confidence * relevance
                    scored_beliefs.append((belief, score))
                    seen_ids.add(belief.id)

        for belief in l3_plus_beliefs:
            if belief.id not in seen_ids:
                score = belief.confidence * 0.5
                scored_beliefs.append((belief, score))
                seen_ids.add(belief.id)

        scored_beliefs.sort(key=lambda x: x[1], reverse=True)

        messages: list[dict[str, Any]] = []
        current_tokens = 0

        for belief, _score in scored_beliefs:
            role = _MEMORY_TYPE_ROLE_MAP.get(belief.memory_type, "system")
            prefix = _layer_prefix(belief.layer, belief.memory_type)

            content = f"{prefix}: {belief.content}"
            estimated_tokens = max(1, len(content) // 4)

            if current_tokens + estimated_tokens > max_tokens:
                continue

            messages.append({"role": role, "content": content})
            current_tokens += estimated_tokens

        logger.debug(
            "BeliefReader: read %d beliefs (%d tokens) for conversation %s",
            len(scored_beliefs),
            current_tokens,
            conversation_id,
        )

        return messages

    async def read_rescue(
        self,
        conversation_id: str,
        user_query: str,
        max_tokens: int = 6000,
    ) -> list[dict[str, Any]]:
        ebl_messages = await self._read_evidence_belief_context(
            conversation_id=conversation_id,
            user_query=user_query,
            max_tokens=max_tokens,
            rescue=True,
        )
        if ebl_messages:
            return ebl_messages
        return await self.read(conversation_id, user_query=user_query, max_tokens=max_tokens)

    async def _read_evidence_belief_context(
        self,
        conversation_id: str,
        user_query: str,
        max_tokens: int,
        rescue: bool = False,
    ) -> list[dict[str, Any]]:
        ebl_reader = get_real_callable_attr(
            self._belief_store,
            "retrieve_evidence_belief_context",
        )
        if ebl_reader is None:
            return []

        try:
            bundle = await ebl_reader(
                conversation_id=conversation_id,
                query=user_query,
                max_tokens=max_tokens,
                rescue=rescue,
            )
            context = str(bundle.get("context") or "")
            if not context:
                return []
            diagnostics = bundle.get("diagnostics") or {}
            return [
                {
                    "role": "system",
                    "content": (
                        f"{context}\n\n"
                        f"Retrieval diagnostics: {diagnostics}"
                    ),
                }
            ]
        except Exception:
            logger.warning("evidence_belief_reader_failed", exc_info=True)
            return []


def _layer_prefix(layer: int, memory_type: str) -> str:
    layer_labels: dict[int, str] = {
        1: "[Core Memory]",
        2: "[Working Memory]",
        3: "[Long-term]",
        4: "[Skill]",
        5: "[Relational]",
        6: "[Persona]",
    }
    base = layer_labels.get(layer, "[Memory]")
    return f"{base}[{memory_type}]"

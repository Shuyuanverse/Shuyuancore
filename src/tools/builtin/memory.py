from __future__ import annotations

import time
import uuid
from typing import Any

from src.core.interfaces import Belief
from src.memory.belief_store import PersistentBeliefStore
from src.memory.interfaces import IEntityExtractor
from src.memory.reader import BeliefReader
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class MemoryTool(ITool):
    VALID_OPERATIONS: frozenset[str] = frozenset(
        {
            "search",
            "read",
            "write",
            "delete",
            "list",
        }
    )

    def __init__(
        self,
        store: PersistentBeliefStore | None = None,
        reader: BeliefReader | None = None,
        entity_extractor: IEntityExtractor | None = None,
    ) -> None:
        self._store = store
        self._reader = reader
        self._entity_extractor = entity_extractor

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="memory",
            description=(
                "记忆管理工具，支持搜索、读取、写入、删除和列出信念。"
                "search 使用 FTS5 全文搜索；read 按 ID 读取信念；"
                "write 写入新信念；delete 删除信念；"
                "list 列出最近信念。"
            ),
            category="memory",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="操作类型：search/read/write/delete/list",
                    required=True,
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索关键词，search 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="信念内容，write 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="layer",
                    type="integer",
                    description="记忆层级（1-6）",
                    required=False,
                    default=3,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="返回结果数量上限",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="belief_id",
                    type="string",
                    description="信念 ID，read/delete 操作必填",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        operation: str = params.get("operation", "")
        if operation not in self.VALID_OPERATIONS:
            errors.append(f"operation 必须是 {', '.join(sorted(self.VALID_OPERATIONS))}")
        if operation == "search" and not params.get("query"):
            errors.append("search 操作需要提供 query 参数")
        if operation in ("read", "delete") and not params.get("belief_id"):
            errors.append(f"{operation} 操作需要提供 belief_id 参数")
        if operation == "write" and not params.get("content"):
            errors.append("write 操作需要提供 content 参数")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        start = time.time()
        operation: str = params["operation"]
        conversation_id: str = user_id

        try:
            if operation == "search":
                result = await self._execute_search(
                    params,
                    conversation_id,
                )
            elif operation == "read":
                result = await self._execute_read(params)
            elif operation == "write":
                result = await self._execute_write(
                    params,
                    conversation_id,
                )
            elif operation == "delete":
                result = await self._execute_delete(
                    params,
                    conversation_id,
                )
            elif operation == "list":
                result = await self._execute_list(
                    params,
                    conversation_id,
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"不支持的操作: {operation}",
                    duration_ms=(time.time() - start) * 1000,
                )

            result.duration_ms = (time.time() - start) * 1000
            return result

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _execute_search(
        self,
        params: dict[str, Any],
        conversation_id: str,
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(success=False, error="记忆存储未初始化")
        query: str = params["query"]
        limit: int = params.get("limit", 10)
        results = await self._store.search_similar(query, top_k=limit)
        beliefs = [
            {
                "id": b.id,
                "content": b.content,
                "layer": b.layer,
                "confidence": b.confidence,
                "memory_type": b.memory_type,
                "timestamp": b.timestamp,
                "status": b.status,
            }
            for b, _score in results
        ]
        return ToolResult(success=True, data={"results": beliefs})

    async def _execute_read(
        self,
        params: dict[str, Any],
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(success=False, error="记忆存储未初始化")
        belief_id: str = params["belief_id"]
        belief = await self._store.get_by_id(belief_id)
        if belief is None:
            return ToolResult(
                success=False,
                error=f"信念 {belief_id} 不存在",
            )
        return ToolResult(
            success=True,
            data={
                "id": belief.id,
                "content": belief.content,
                "source": belief.source,
                "layer": belief.layer,
                "confidence": belief.confidence,
                "memory_type": belief.memory_type,
                "status": belief.status,
                "timestamp": belief.timestamp,
                "entities": belief.entities,
                "emotion": belief.emotion,
                "metadata": belief.metadata,
            },
        )

    async def _execute_write(
        self,
        params: dict[str, Any],
        conversation_id: str,
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(success=False, error="记忆存储未初始化")
        content: str = params["content"]
        layer: int = params.get("layer", 3)
        entities: list[str] = []
        if self._entity_extractor is not None:
            entities = self._entity_extractor.extract(content)
        belief = Belief(
            id=str(uuid.uuid4()),
            content=content,
            source="tool",
            layer=layer,
            memory_type="chat",
            entities=entities,
        )
        belief_id = await self._store.add(conversation_id, belief)
        return ToolResult(
            success=True,
            data={"belief_id": belief_id, "layer": layer},
        )

    async def _execute_delete(
        self,
        params: dict[str, Any],
        conversation_id: str,
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(success=False, error="记忆存储未初始化")
        belief_id: str = params["belief_id"]
        await self._store.remove(conversation_id, belief_id)
        return ToolResult(
            success=True,
            data={"deleted": belief_id},
        )

    async def _execute_list(
        self,
        params: dict[str, Any],
        conversation_id: str,
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(success=False, error="记忆存储未初始化")
        limit: int = params.get("limit", 10)
        beliefs = await self._store.get(conversation_id, limit=limit)
        return ToolResult(
            success=True,
            data={
                "results": [
                    {
                        "id": b.id,
                        "content": b.content,
                        "layer": b.layer,
                        "confidence": b.confidence,
                        "memory_type": b.memory_type,
                        "timestamp": b.timestamp,
                        "status": b.status,
                    }
                    for b in beliefs
                ],
            },
        )

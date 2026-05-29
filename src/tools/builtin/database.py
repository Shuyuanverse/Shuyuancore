from __future__ import annotations

import time
from typing import Any

import aiosqlite

from src.config import get_settings
from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class DatabaseTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="database",
            description="数据库查询工具，支持执行 SQL 查询和写入操作。",
            category="web",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="SQL 查询语句",
                    required=True,
                ),
                ToolParameter(
                    name="params",
                    type="array",
                    description="查询参数列表",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="查询超时时间（秒）",
                    required=False,
                    default=30,
                ),
                ToolParameter(
                    name="db_path",
                    type="string",
                    description="数据库文件路径",
                    required=False,
                    default="data/state.db",
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        query = params.get("query", "")
        if not query or not isinstance(query, str) or not query.strip():
            errors.append("query 参数不能为空")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        query: str = params["query"]
        query_params: list[Any] | None = params.get("params")
        timeout: int = params.get("timeout", 30)
        db_path: str = params.get("db_path", "data/state.db")
        start = time.time()
        audit = get_audit_logger()

        is_write = self._is_write_query(query)

        if is_write:
            config = get_settings().tools
            if config.database_readonly:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="database.execute",
                    resource=f"db:{db_path}",
                    params={"query": query[:100]},
                    result="rejected_readonly",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error="数据库处于只读模式，不允许写入操作",
                    duration_ms=duration_ms,
                )
            approval_mgr = await get_approval_manager()
            req = await approval_mgr.request(
                tool_name="database",
                params=params,
                user_id=user_id,
                timeout=get_settings().tools.approval_timeout,
            )
            approved = await approval_mgr.wait(
                req.approval_id,
                timeout=get_settings().tools.approval_timeout,
            )
            if not approved:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="database.execute",
                    resource=f"db:{db_path}",
                    params={"query": query[:100]},
                    result="rejected",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error="写入操作未获批准",
                    duration_ms=duration_ms,
                    approval_id=req.approval_id,
                )

        try:
            async with aiosqlite.connect(db_path, timeout=timeout) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query, query_params or [])
                if is_write:
                    await db.commit()
                    affected = cursor.rowcount
                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="database.execute",
                        resource=f"db:{db_path}",
                        params={"query": query[:100]},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={"affected_rows": affected},
                        duration_ms=duration_ms,
                    )
                rows = await cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                result = [dict(zip(columns, row)) for row in rows]
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="database.execute",
                    resource=f"db:{db_path}",
                    params={"query": query[:100]},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={"rows": result, "count": len(result)},
                    duration_ms=duration_ms,
                )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="database.execute",
                resource=f"db:{db_path}",
                params={"query": query[:100]},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"数据库查询失败: {e}",
                duration_ms=duration_ms,
            )

    @staticmethod
    def _is_write_query(query: str) -> bool:
        stripped = query.strip()
        if not stripped:
            return False
        return not stripped.upper().startswith("SELECT")

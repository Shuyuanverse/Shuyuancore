# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.config import WorkingMemoryConfig, get_settings
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


@dataclass
class TodoItem:
    id: str
    project_name: str
    content: str
    status: str
    priority: int
    created_at: int
    updated_at: int
    completed_at: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingMemoryContext:
    project_name: str
    todos: list[TodoItem]
    notes: str
    created_at: int
    updated_at: int
    last_accessed_at: int
    is_archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    def __init__(
        self,
        db_path: str = _DB_PATH,
        config: WorkingMemoryConfig | None = None,
    ) -> None:
        self._db_path: str = db_path
        self._config: WorkingMemoryConfig = config or get_settings().memory.working
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._init_tables()
        return self._conn

    async def _init_tables(self) -> None:
        conn = await self._get_conn()

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS working_memory_projects (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL UNIQUE,
                notes TEXT DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                last_accessed_at INTEGER NOT NULL DEFAULT 0,
                is_archived INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT DEFAULT '{}'
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS working_memory_todos (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                completed_at INTEGER,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (project_id) REFERENCES working_memory_projects(id)
                    ON DELETE CASCADE
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_todos_project_id
            ON working_memory_todos(project_id, status, priority DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_projects_last_accessed
            ON working_memory_projects(last_accessed_at DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_projects_archived
            ON working_memory_projects(is_archived, last_accessed_at);
            """
        )

        await conn.commit()

    async def activate(self, project_name: str) -> WorkingMemoryContext:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        cursor = await conn.execute(
            "SELECT id FROM working_memory_projects WHERE project_name = ?",
            (project_name,),
        )
        row = await cursor.fetchone()

        if row is None:
            project_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO working_memory_projects
                    (id, project_name, notes, created_at, updated_at, last_accessed_at)
                VALUES (?, '', '', ?, ?, ?)
                """,
                (project_id, now_ms, now_ms, now_ms),
            )
            logger.info("Created new working memory project: %s", project_name)
        else:
            project_id = row["id"]
            await conn.execute(
                """
                UPDATE working_memory_projects
                SET last_accessed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now_ms, now_ms, project_id),
            )

        await conn.commit()
        return await self.get_context(project_name)

    async def add_todo(
        self,
        project_name: str,
        content: str,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> TodoItem:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        cursor = await conn.execute(
            "SELECT id FROM working_memory_projects WHERE project_name = ?",
            (project_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Project '{project_name}' not found. Call activate() first.")

        project_id = row["id"]
        todo_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO working_memory_todos
                (id, project_id, content, status, priority, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (todo_id, project_id, content, priority, now_ms, now_ms, json.dumps(metadata or {})),
        )

        await conn.execute(
            """
            UPDATE working_memory_projects
            SET updated_at = ?
            WHERE id = ?
            """,
            (now_ms, project_id),
        )

        await conn.commit()

        return TodoItem(
            id=todo_id,
            project_name=project_name,
            content=content,
            status="pending",
            priority=priority,
            created_at=now_ms,
            updated_at=now_ms,
            metadata=metadata or {},
        )

    async def complete_todo(self, todo_id: str) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            UPDATE working_memory_todos
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now_ms, now_ms, todo_id),
        )

        cursor = await conn.execute(
            """
            SELECT project_id FROM working_memory_todos WHERE id = ?
            """,
            (todo_id,),
        )
        row = await cursor.fetchone()
        if row is not None:
            await conn.execute(
                """
                UPDATE working_memory_projects
                SET updated_at = ?
                WHERE id = ?
                """,
                (now_ms, row["project_id"]),
            )

        await conn.commit()
        logger.debug("Completed todo: %s", todo_id)

    async def get_context(self, project_name: str) -> WorkingMemoryContext:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT id, project_name, notes, created_at, updated_at,
                   last_accessed_at, is_archived, metadata_json
            FROM working_memory_projects
            WHERE project_name = ?
            """,
            (project_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Project '{project_name}' not found")

        todos_cursor = await conn.execute(
            """
            SELECT id, content, status, priority, created_at, updated_at,
                   completed_at, metadata_json
            FROM working_memory_todos
            WHERE project_id = ?
            ORDER BY priority DESC, created_at ASC
            """,
            (row["id"],),
        )
        todo_rows = await todos_cursor.fetchall()

        todos = [
            TodoItem(
                id=todo_row["id"],
                project_name=project_name,
                content=todo_row["content"],
                status=todo_row["status"],
                priority=todo_row["priority"],
                created_at=todo_row["created_at"],
                updated_at=todo_row["updated_at"],
                completed_at=todo_row["completed_at"],
                metadata=json.loads(todo_row["metadata_json"]) if todo_row["metadata_json"] else {},
            )
            for todo_row in todo_rows
        ]

        return WorkingMemoryContext(
            project_name=project_name,
            todos=todos,
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
            is_archived=bool(row["is_archived"]),
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    async def add_note(self, project_name: str, note: str) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        cursor = await conn.execute(
            "SELECT id FROM working_memory_projects WHERE project_name = ?",
            (project_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Project '{project_name}' not found")

        await conn.execute(
            """
            UPDATE working_memory_projects
            SET notes = notes || ?, updated_at = ?, last_accessed_at = ?
            WHERE id = ?
            """,
            (note + "\n", now_ms, now_ms, row["id"]),
        )

        await conn.commit()
        logger.debug("Added note to project: %s", project_name)

    async def archive_project(self, project_name: str) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            UPDATE working_memory_projects
            SET is_archived = 1, updated_at = ?, last_accessed_at = ?
            WHERE project_name = ?
            """,
            (now_ms, now_ms, project_name),
        )

        await conn.commit()
        logger.info("Archived project: %s", project_name)

    async def auto_archive_expired(self) -> int:
        if not self._config.auto_cleanup:
            return 0

        conn = await self._get_conn()
        now_ms = current_time_ms()
        expire_ms = self._config.expire_days * 24 * 60 * 60 * 1000

        cursor = await conn.execute(
            """
            UPDATE working_memory_projects
            SET is_archived = 1, updated_at = ?
            WHERE is_archived = 0
              AND last_accessed_at < ?
            """,
            (now_ms, now_ms - expire_ms),
        )

        archived_count = cursor.rowcount
        await conn.commit()

        if archived_count > 0:
            logger.info("Auto-archived %d expired projects", archived_count)

        return archived_count

    async def list_projects(
        self,
        include_archived: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()

        archived_filter = "" if include_archived else "WHERE is_archived = 0"

        cursor = await conn.execute(
            f"""
            SELECT project_name, created_at, updated_at, last_accessed_at, is_archived
            FROM working_memory_projects
            {archived_filter}
            ORDER BY last_accessed_at DESC
            LIMIT ?
            """,
            (limit,),
        )

        rows = await cursor.fetchall()
        return [
            {
                "project_name": row["project_name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_accessed_at": row["last_accessed_at"],
                "is_archived": bool(row["is_archived"]),
            }
            for row in rows
        ]

    async def delete_project(self, project_name: str) -> None:
        conn = await self._get_conn()

        await conn.execute(
            """
            DELETE FROM working_memory_projects
            WHERE project_name = ?
            """,
            (project_name,),
        )

        await conn.commit()
        logger.info("Deleted project: %s", project_name)

    async def get_statistics(self) -> dict[str, Any]:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total_projects,
                SUM(CASE WHEN is_archived = 0 THEN 1 ELSE 0 END) as active_projects,
                SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived_projects
            FROM working_memory_projects
            """,
        )
        project_stats = await cursor.fetchone()

        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total_todos,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_todos,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_todos
            FROM working_memory_todos
            """,
        )
        todo_stats = await cursor.fetchone()

        return {
            "total_projects": project_stats["total_projects"] or 0,
            "active_projects": project_stats["active_projects"] or 0,
            "archived_projects": project_stats["archived_projects"] or 0,
            "total_todos": todo_stats["total_todos"] or 0,
            "completed_todos": todo_stats["completed_todos"] or 0,
            "pending_todos": todo_stats["pending_todos"] or 0,
        }

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

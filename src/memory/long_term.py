# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""SQLite 持久化长时记忆存储 — 支持 FTS5 全文检索和分层管理。

使用指引：
- LongTermMemory 是生产级实现，适合大规模场景
- 自动建表、FTS5 索引、WAL 模式
- 提供 store_entry / retrieve_similar / consolidate / cleanup 等完整接口
- 轻量测试请使用 src.core.belief_store.BeliefStore
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import aiosqlite

from src.memory.base import MemoryEntry, MemoryStats
from src.memory.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


class LongTermMemory:
    def __init__(
        self,
        db_path: str = _DB_PATH,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._db_path: str = db_path
        self._embedding_service: EmbeddingService | None = embedding_service
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
            CREATE TABLE IF NOT EXISTS long_term_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'general',
                layer INTEGER NOT NULL DEFAULT 3,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                is_consolidated INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ltm_layer
            ON long_term_memories(layer, created_at DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ltm_type
            ON long_term_memories(memory_type, created_at DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ltm_created
            ON long_term_memories(created_at);
            """
        )

        try:
            await conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS long_term_memories_fts USING fts5(
                    content,
                    content='long_term_memories',
                    content_rowid='rowid'
                );
                """
            )
        except aiosqlite.OperationalError:
            logger.warning("FTS5 not available, falling back to LIKE search")

        await conn.commit()

    async def store_entry(self, entry: MemoryEntry) -> str:
        conn = await self._get_conn()
        now = int(time.time() * 1000)
        entry_id = entry.id or str(uuid.uuid4())
        metadata_json = json.dumps(entry.metadata, ensure_ascii=False)
        created_at = entry.created_at or now
        last_accessed = entry.last_accessed or now

        await conn.execute(
            """
            INSERT INTO long_term_memories
                (id, content, memory_type, layer, confidence,
                 created_at, last_accessed, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                entry.content,
                entry.memory_type,
                entry.layer,
                entry.confidence,
                created_at,
                last_accessed,
                metadata_json,
            ),
        )

        try:
            await conn.execute(
                "INSERT INTO long_term_memories_fts(rowid, content) "
                "VALUES (last_insert_rowid(), ?);",
                (entry.content,),
            )
        except Exception:
            pass

        await conn.commit()
        logger.debug("Long-term memory stored: id=%s type=%s", entry_id, entry.memory_type)
        return entry_id

    async def retrieve_similar(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[MemoryEntry, float]]:
        conn = await self._get_conn()
        sanitized = query.strip()
        if not sanitized:
            return []

        results: list[tuple[MemoryEntry, float]] = []
        seen_ids: set[str] = set()

        try:
            fts_query = " OR ".join(f'"{w}"' for w in sanitized.split() if w)
            cursor = await conn.execute(
                """
                SELECT m.*, rank
                FROM long_term_memories_fts fts
                JOIN long_term_memories m ON m.rowid = fts.rowid
                WHERE long_term_memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, top_k),
            )
            rows = await cursor.fetchall()
            for row in rows:
                entry = self._row_to_entry(row)
                if entry.id not in seen_ids:
                    rank = row["rank"] if "rank" in row.keys() else 0.0
                    score = 1.0 / (1.0 + abs(rank))
                    score = max(0.0, min(1.0, score))
                    results.append((entry, score))
                    seen_ids.add(entry.id)
        except aiosqlite.OperationalError:
            pass

        cursor = await conn.execute(
            """
            SELECT * FROM long_term_memories
            WHERE content LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{sanitized}%", top_k),
        )
        rows = await cursor.fetchall()
        for row in rows:
            entry = self._row_to_entry(row)
            if entry.id not in seen_ids:
                results.append((entry, 0.5))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def retrieve_by_time_range(
        self,
        start_ms: int,
        end_ms: int,
    ) -> list[MemoryEntry]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM long_term_memories
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (start_ms, end_ms),
        )
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def retrieve_by_type(
        self,
        memory_type: str,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM long_term_memories
            WHERE memory_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (memory_type, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def update_last_accessed(self, entry_id: str) -> None:
        conn = await self._get_conn()
        now = int(time.time() * 1000)
        await conn.execute(
            "UPDATE long_term_memories SET last_accessed = ? WHERE id = ?",
            (now, entry_id),
        )
        await conn.commit()

    async def consolidate(self) -> int:
        conn = await self._get_conn()
        now = int(time.time() * 1000)
        cutoff = now - 7 * 24 * 60 * 60 * 1000

        cursor = await conn.execute(
            """
            UPDATE long_term_memories
            SET is_consolidated = 1
            WHERE is_consolidated = 0
              AND created_at < ?
              AND layer >= 3
            """,
            (cutoff,),
        )
        affected = cursor.rowcount
        if affected > 0:
            await conn.commit()
            logger.info("Consolidated %d long-term memories", affected)
        return affected

    async def cleanup(self, max_entries: int = 10000) -> int:
        conn = await self._get_conn()

        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM long_term_memories",
        )
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

        if total <= max_entries:
            return 0

        excess = total - max_entries
        cursor = await conn.execute(
            """
            SELECT rowid, id FROM long_term_memories
            ORDER BY last_accessed ASC
            LIMIT ?
            """,
            (excess,),
        )
        to_remove = await cursor.fetchall()

        removed = 0
        for r in to_remove:
            try:
                await conn.execute(
                    "INSERT INTO long_term_memories_fts(long_term_memories_fts, rowid, content) "
                    "VALUES('delete', ?, '');",
                    (r["rowid"],),
                )
            except Exception:
                pass
            await conn.execute(
                "DELETE FROM long_term_memories WHERE id = ?",
                (r["id"],),
            )
            removed += 1

        await conn.commit()
        logger.info(
            "Cleaned up %d long-term memories (kept %d)",
            removed,
            max_entries,
        )
        return removed

    async def get_statistics(self) -> MemoryStats:
        conn = await self._get_conn()

        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM long_term_memories")
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

        by_layer: dict[int, int] = {}
        cursor = await conn.execute(
            "SELECT layer, COUNT(*) as cnt FROM long_term_memories GROUP BY layer",
        )
        for r in await cursor.fetchall():
            by_layer[r["layer"]] = r["cnt"]

        by_type: dict[str, int] = {}
        cursor = await conn.execute(
            "SELECT memory_type, COUNT(*) as cnt FROM long_term_memories GROUP BY memory_type",
        )
        for r in await cursor.fetchall():
            by_type[r["memory_type"]] = r["cnt"]

        cursor = await conn.execute(
            "SELECT SUM(LENGTH(content)) as total_bytes FROM long_term_memories",
        )
        row = await cursor.fetchone()
        total_bytes = row["total_bytes"] if row and row["total_bytes"] else 0

        cursor = await conn.execute(
            "SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM long_term_memories",
        )
        row = await cursor.fetchone()
        oldest = row["oldest"] if row and row["oldest"] else 0
        newest = row["newest"] if row and row["newest"] else 0

        return MemoryStats(
            total_entries=total,
            by_layer=by_layer,
            by_type=by_type,
            total_size_bytes=total_bytes,
            oldest_entry=oldest,
            newest_entry=newest,
        )

    async def get_entry_by_id(self, entry_id: str) -> MemoryEntry | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM long_term_memories WHERE id = ?",
            (entry_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _row_to_entry(self, row: aiosqlite.Row) -> MemoryEntry:
        metadata = {}
        raw_meta = row["metadata_json"]
        if raw_meta and raw_meta != "{}":
            try:
                metadata = json.loads(raw_meta)
            except json.JSONDecodeError:
                metadata = {}

        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            memory_type=row["memory_type"],
            layer=row["layer"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            metadata=metadata,
        )
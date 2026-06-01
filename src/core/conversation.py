# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import aiosqlite

from src.config import get_settings
from src.core.interfaces import IConversationManager
from src.gateway.utils import decode_cursor, encode_cursor

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE: int = 20
_MAX_PAGE_SIZE: int = 100
_MAX_MESSAGES: int = 200


class ConversationManager(IConversationManager):
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path: str = db_path or get_settings().database.db_path
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
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conv_user
            ON conversations(user_id, updated_at DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conv_deleted
            ON conversations(is_deleted);
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_msg_conv
            ON messages(conversation_id, created_at DESC, id DESC);
            """
        )

        await conn.commit()

    async def create_conversation(self, user_id: str, title: str = "") -> str:
        conn = await self._get_conn()
        conversation_id = str(uuid.uuid4())
        now = int(time.time() * 1000)

        await conn.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, user_id, title, now, now),
        )
        await conn.commit()
        logger.info(
            "Conversation created: id=%s user=%s title=%s",
            conversation_id,
            user_id,
            title,
        )
        return conversation_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn = await self._get_conn()
        message_id = str(uuid.uuid4())
        now = int(time.time() * 1000)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        await conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, role, content, metadata_json, now),
        )

        await conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await conn.commit()

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        effective_limit = min(max(limit, 1), _MAX_MESSAGES)

        params: list[Any]
        if before is not None:
            decoded = decode_cursor(before)
            if decoded is None:
                logger.warning("Invalid before cursor: %s", before)
                decoded = None
            if decoded is not None:
                cursor_ts, cursor_id = decoded
                query = """
                    SELECT id, conversation_id, role, content, metadata_json, created_at
                    FROM messages
                    WHERE conversation_id = ?
                      AND (created_at < ? OR (created_at = ? AND id < ?))
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                """
                params = [conversation_id, cursor_ts, cursor_ts, cursor_id, effective_limit]
            else:
                query = """
                    SELECT id, conversation_id, role, content, metadata_json, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                """
                params = [conversation_id, effective_limit]
        else:
            query = """
                SELECT id, conversation_id, role, content, metadata_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """
            params = [conversation_id, effective_limit]

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

        messages: list[dict[str, Any]] = []
        for row in reversed(rows):
            metadata = {}
            raw_meta = row["metadata_json"]
            if raw_meta and raw_meta != "{}":
                try:
                    metadata = json.loads(raw_meta)
                except json.JSONDecodeError:
                    metadata = {}

            messages.append(
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "metadata": metadata,
                }
            )

        return messages

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, bool]:
        conn = await self._get_conn()
        effective_limit = min(max(limit, 1), _MAX_PAGE_SIZE) + 1

        params: list[Any]
        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is None:
                return [], None, False
            cursor_ts, cursor_id = decoded
            query = """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = ? AND is_deleted = 0
                  AND (updated_at < ? OR (updated_at = ? AND id < ?))
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
            """
            params = [user_id, cursor_ts, cursor_ts, cursor_id, effective_limit]
        else:
            query = """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = ? AND is_deleted = 0
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
            """
            params = [user_id, effective_limit]

        db_cursor = await conn.execute(query, params)
        rows = list(await db_cursor.fetchall())
        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(last["updated_at"], last["id"])

        return items, next_cursor, has_more

    async def delete_conversation(self, conversation_id: str) -> None:
        conn = await self._get_conn()
        now = int(time.time() * 1000)

        await conn.execute(
            "UPDATE conversations SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await conn.commit()
        logger.info("Conversation deleted (soft): id=%s", conversation_id)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

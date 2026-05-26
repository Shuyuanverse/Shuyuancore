from __future__ import annotations

import json
import logging
import uuid

import aiosqlite

from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms
from src.memory.embedding import EmbeddingService
from src.memory.propagation import overthrow as propagation_overthrow
from src.memory.propagation import propagate_confidence as propagation_propagate
from src.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


def _belief_from_row(row: aiosqlite.Row) -> Belief:
    return Belief(
        id=row["id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        base_confidence=row["base_confidence"],
        last_accessed=row["last_accessed"],
        memory_type=row["memory_type"],
        layer=row["layer"],
        entities=json.loads(row["entities"]) if row["entities"] else [],
        emotion=row["emotion"],
        depends_on=json.loads(row["depends_on"]) if row["depends_on"] else [],
        child_belief_ids=json.loads(row["child_belief_ids"]) if row["child_belief_ids"] else [],
        superseded_by=row["superseded_by"],
        status=row["status"],
        is_composite=bool(row["is_composite"]),
        timestamp=row["timestamp"],
        metadata=(
            json.loads(row["metadata_json"])
            if row["metadata_json"] and row["metadata_json"] != "{}"
            else {}
        ),
    )


class PersistentBeliefStore(IBeliefStore):

    def __init__(
        self,
        db_path: str = _DB_PATH,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._db_path: str = db_path
        self._embedding_service: EmbeddingService | None = embedding_service
        self._vector_store: VectorStore | None = vector_store
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
            CREATE TABLE IF NOT EXISTS beliefs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'user',
                confidence REAL NOT NULL DEFAULT 1.0,
                base_confidence REAL NOT NULL DEFAULT 1.0,
                last_accessed INTEGER NOT NULL DEFAULT 0,
                memory_type TEXT NOT NULL DEFAULT 'chat',
                layer INTEGER NOT NULL DEFAULT 3,
                entities TEXT DEFAULT '[]',
                emotion REAL NOT NULL DEFAULT 0.5,
                depends_on TEXT DEFAULT '[]',
                child_belief_ids TEXT DEFAULT '[]',
                superseded_by TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                is_composite INTEGER NOT NULL DEFAULT 0,
                timestamp INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT DEFAULT '{}',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_conversation
            ON beliefs(conversation_id, layer, timestamp DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_status
            ON beliefs(status, confidence DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_layer
            ON beliefs(layer, confidence DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_user_id
            ON beliefs(user_id);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_beliefs_user_conv
            ON beliefs(user_id, conversation_id, layer);
            """
        )

        await conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS beliefs_fts USING fts5(
                content,
                content='beliefs',
                content_rowid='rowid'
            );
            """
        )

        await conn.commit()

    async def add(
        self,
        conversation_id: str,
        belief: Belief,
        user_id: str = "anonymous",
    ) -> str:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        belief_id = belief.id or str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO beliefs (
                id, conversation_id, user_id, content, source,
                confidence, base_confidence, last_accessed,
                memory_type, layer, entities, emotion,
                depends_on, child_belief_ids, superseded_by,
                status, is_composite, timestamp, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                belief_id,
                conversation_id,
                user_id,
                belief.content,
                belief.source,
                belief.confidence,
                belief.base_confidence,
                belief.last_accessed or now_ms,
                belief.memory_type,
                belief.layer,
                json.dumps(belief.entities, ensure_ascii=False),
                belief.emotion,
                json.dumps(belief.depends_on),
                json.dumps(belief.child_belief_ids),
                belief.superseded_by,
                belief.status,
                1 if belief.is_composite else 0,
                belief.timestamp or now_ms,
                json.dumps(belief.metadata, ensure_ascii=False),
                now_ms,
                now_ms,
            ),
        )

        await conn.execute(
            "INSERT INTO beliefs_fts(rowid, content) VALUES (last_insert_rowid(), ?);",
            (belief.content,),
        )

        await conn.commit()
        logger.debug("Belief added: %s -> %s", belief_id, belief.content[:60])

        if self._embedding_service and self._vector_store:
            try:
                vector = await self._embedding_service.embed(belief.content)
                if vector is not None:
                    await self._vector_store.add(
                        belief_id,
                        vector,
                        metadata={
                            "layer": str(belief.layer),
                            "conversation_id": conversation_id,
                        },
                    )
            except Exception:
                logger.warning(
                    "vector_embedding_skipped belief_id=%s",
                    belief_id,
                    exc_info=True,
                )

        return belief_id

    async def get(
        self, conversation_id: str, limit: int = 50
    ) -> list[Belief]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM beliefs
            WHERE conversation_id = ? AND status = 'active'
            ORDER BY layer ASC, timestamp DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        )
        rows = await cursor.fetchall()
        return [_belief_from_row(row) for row in rows]

    async def get_by_id(self, belief_id: str) -> Belief | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM beliefs WHERE id = ?",
            (belief_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _belief_from_row(row)

    async def update(self, belief: Belief) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            UPDATE beliefs SET
                content = ?, source = ?,
                confidence = ?, base_confidence = ?,
                last_accessed = ?,
                memory_type = ?, layer = ?,
                entities = ?, emotion = ?,
                depends_on = ?, child_belief_ids = ?,
                superseded_by = ?, status = ?,
                is_composite = ?, timestamp = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                belief.content,
                belief.source,
                belief.confidence,
                belief.base_confidence,
                belief.last_accessed,
                belief.memory_type,
                belief.layer,
                json.dumps(belief.entities, ensure_ascii=False),
                belief.emotion,
                json.dumps(belief.depends_on),
                json.dumps(belief.child_belief_ids),
                belief.superseded_by,
                belief.status,
                1 if belief.is_composite else 0,
                belief.timestamp,
                json.dumps(belief.metadata, ensure_ascii=False),
                now_ms,
                belief.id,
            ),
        )

        await conn.execute(
            "INSERT INTO beliefs_fts(beliefs_fts, rowid, content) "
            "VALUES('delete', (SELECT rowid FROM beliefs WHERE id = ?), ?);",
            (belief.id, belief.content),
        )
        await conn.execute(
            "INSERT INTO beliefs_fts(rowid, content) "
            "VALUES ((SELECT rowid FROM beliefs WHERE id = ?), ?);",
            (belief.id, belief.content),
        )

        await conn.commit()

    async def clear(self, conversation_id: str) -> None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT rowid FROM beliefs WHERE conversation_id = ?",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await conn.execute(
                "INSERT INTO beliefs_fts(beliefs_fts, rowid, content) VALUES('delete', ?, '');",
                (row["rowid"],),
            )

        await conn.execute(
            "DELETE FROM beliefs WHERE conversation_id = ?",
            (conversation_id,),
        )
        await conn.commit()

    async def remove(self, conversation_id: str, belief_id: str) -> None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT rowid FROM beliefs WHERE id = ? AND conversation_id = ?",
            (belief_id, conversation_id),
        )
        row = await cursor.fetchone()
        if row is not None:
            await conn.execute(
                "INSERT INTO beliefs_fts(beliefs_fts, rowid, content) VALUES('delete', ?, '');",
                (row["rowid"],),
            )

        await conn.execute(
            "DELETE FROM beliefs WHERE id = ? AND conversation_id = ?",
            (belief_id, conversation_id),
        )
        await conn.commit()

    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]:
        sanitized = query.strip()
        if not sanitized:
            return []

        results: list[tuple[Belief, float]] = []
        seen_ids: set[str] = set()

        if self._vector_store and self._embedding_service:
            try:
                query_vector = await self._embedding_service.embed(sanitized)
                if query_vector is not None:
                    vector_results = await self._vector_store.search(
                        query_vector, top_k
                    )
                    for belief_id, score in vector_results:
                        belief = await self.get_by_id(belief_id)
                        if (
                            belief is not None
                            and belief.status == "active"
                            and belief.confidence >= min_confidence
                            and belief.id not in seen_ids
                        ):
                            results.append((belief, score))
                            seen_ids.add(belief.id)
            except Exception:
                logger.warning(
                    "vector_search_failed, falling back to text search",
                    exc_info=True,
                )

        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """
                SELECT b.*, rank
                FROM beliefs_fts
                JOIN beliefs b ON b.rowid = beliefs_fts.rowid
                WHERE beliefs_fts MATCH ?
                  AND b.status = 'active'
                  AND b.confidence >= ?
                ORDER BY rank
                LIMIT ?
                """,
                (sanitized, min_confidence, top_k),
            )
            rows = await cursor.fetchall()
            if rows:
                for row in rows:
                    belief = _belief_from_row(row)
                    if belief.id not in seen_ids:
                        rank = row["rank"] if "rank" in row.keys() else 0.0
                        score = 1.0 / (1.0 + abs(rank))
                        score = max(0.0, min(1.0, score))
                        results.append((belief, score))
                        seen_ids.add(belief.id)
        except aiosqlite.OperationalError:
            pass

        cursor = await conn.execute(
            """
            SELECT * FROM beliefs
            WHERE content LIKE ?
              AND status = 'active'
              AND confidence >= ?
            LIMIT ?
            """,
            (f"%{sanitized}%", min_confidence, top_k),
        )
        rows = await cursor.fetchall()
        for row in rows:
            belief = _belief_from_row(row)
            if belief.id not in seen_ids:
                results.append((belief, 0.5))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None:
        await propagation_propagate(self, belief_id, delta, visited)

    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None:
        await propagation_overthrow(self, old_id, new_id, reason)

    async def get_conversation_list(
        self,
        user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[dict[str, object]], str | None, bool]:
        from src.gateway.utils import decode_cursor, encode_cursor

        conn = await self._get_conn()
        effective_limit = min(max(limit, 1), 100) + 1

        user_filter = "AND user_id = ?" if user_id else ""
        params: list[object]

        base_params: list[object] = [user_id] if user_id else []

        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is None:
                return [], None, False
            cursor_ts, cursor_id = decoded
            query = f"""
                SELECT
                    conversation_id,
                    COUNT(*) AS message_count,
                    MIN(timestamp) AS created_at,
                    MAX(timestamp) AS last_message_at
                FROM beliefs
                WHERE layer = 3
                  AND status = 'active'
                  {user_filter}
                GROUP BY conversation_id
                HAVING (MAX(timestamp) < ? OR (MAX(timestamp) = ? AND conversation_id < ?))
                ORDER BY last_message_at DESC, conversation_id DESC
                LIMIT ?
            """
            params = base_params + [cursor_ts, cursor_ts, cursor_id, effective_limit]
        else:
            query = f"""
                SELECT
                    conversation_id,
                    COUNT(*) AS message_count,
                    MIN(timestamp) AS created_at,
                    MAX(timestamp) AS last_message_at
                FROM beliefs
                WHERE layer = 3
                  AND status = 'active'
                  {user_filter}
                GROUP BY conversation_id
                ORDER BY last_message_at DESC, conversation_id DESC
                LIMIT ?
            """
            params = base_params + [effective_limit]

        cursor_obj = await conn.execute(query, params)
        rows_raw = await cursor_obj.fetchall()
        has_more = len(rows_raw) > limit
        rows_raw = rows_raw[:limit]

        items: list[dict[str, object]] = []
        for row in rows_raw:
            items.append(
                {
                    "id": row[0],
                    "message_count": row[1],
                    "created_at": row[2],
                    "last_message_at": row[3],
                }
            )

        next_cursor: str | None = None
        if has_more and rows_raw:
            last = rows_raw[-1]
            next_cursor = encode_cursor(last[3], last[0])

        return items, next_cursor, has_more

    async def get_conversation_messages(
        self,
        conversation_id: str,
        user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, object]], str | None, bool]:
        from src.gateway.utils import decode_cursor, encode_cursor

        conn = await self._get_conn()
        effective_limit = min(max(limit, 1), 200) + 1

        user_filter = "AND user_id = ?" if user_id else ""

        params: list[object]
        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is None:
                return [], None, False
            cursor_ts, cursor_id = decoded
            query = f"""
                SELECT id, content, source, timestamp
                FROM beliefs
                WHERE conversation_id = ?
                  AND layer = 3
                  AND status = 'active'
                  {user_filter}
                  AND (timestamp > ? OR (timestamp = ? AND id > ?))
                ORDER BY timestamp ASC, id ASC
                LIMIT ?
            """
            if user_id:
                params = [
                    conversation_id, user_id,
                    cursor_ts, cursor_ts, cursor_id, effective_limit,
                ]
            else:
                params = [
                    conversation_id,
                    cursor_ts, cursor_ts, cursor_id, effective_limit,
                ]
        else:
            query = f"""
                SELECT id, content, source, timestamp
                FROM beliefs
                WHERE conversation_id = ?
                  AND layer = 3
                  AND status = 'active'
                  {user_filter}
                ORDER BY timestamp ASC, id ASC
                LIMIT ?
            """
            if user_id:
                params = [conversation_id, user_id, effective_limit]
            else:
                params = [conversation_id, effective_limit]

        cursor_obj = await conn.execute(query, params)
        rows_raw = await cursor_obj.fetchall()
        has_more = len(rows_raw) > limit
        rows_raw = rows_raw[:limit]

        items: list[dict[str, object]] = []
        for row in rows_raw:
            items.append(
                {
                    "id": row[0],
                    "content": row[1],
                    "role": row[2],
                    "created_at": row[3],
                }
            )

        next_cursor: str | None = None
        if has_more and rows_raw:
            last = rows_raw[-1]
            next_cursor = encode_cursor(last[3], last[0])

        return items, next_cursor, has_more

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

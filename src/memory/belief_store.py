from __future__ import annotations

import json
import logging
import re
import time
import uuid

import aiosqlite

from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms
from src.memory.embedding import EmbeddingService
from src.memory.propagation import overthrow as propagation_overthrow
from src.memory.propagation import propagate_confidence as propagation_propagate
from src.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

_EVIDENCE_VECTOR_PREFIX = "evidence:"
_CHINESE_PATTERN = None
_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}|"
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?|yesterday|today|tomorrow|last\s+week|next\s+week)\b",
    re.IGNORECASE,
)
_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "when",
    "where",
    "who",
    "why",
    "how",
    "did",
    "does",
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "了",
    "的",
    "是",
    "在",
}


def _has_chinese(text: str) -> bool:
    global _CHINESE_PATTERN
    if _CHINESE_PATTERN is None:
        import re

        _CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
    return bool(_CHINESE_PATTERN.search(text))


def _tokenize_fts_query(query: str) -> str:
    if not _has_chinese(query):
        return query
    try:
        import jieba

        words = list(jieba.cut(query, cut_all=False))
        words = [w.strip() for w in words if w.strip()]
        if not words:
            return query
        fts_parts = " OR ".join(f'"{w}"' for w in words if len(w) > 1)
        for w in words:
            if len(w) == 1:
                fts_parts = fts_parts + f" {w}" if fts_parts else w
        if not fts_parts:
            return query
        return fts_parts
    except ImportError:
        logger.warning("jieba not available, using raw query for FTS5")
        return query


def _json_loads(value: str | None, default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _query_terms(text: str) -> list[str]:
    terms: list[str] = []
    for term in _TERM_PATTERN.findall(text or ""):
        normalized = term.lower()
        if normalized in _STOPWORDS or len(normalized) < 2:
            continue
        terms.append(normalized)
    return terms


def _fts_match_query(text: str) -> str:
    terms = _query_terms(text)
    if not terms:
        return _tokenize_fts_query(text.strip())
    return " OR ".join(f'"{term}"' for term in terms[:12])


def _date_mentions(text: str) -> list[str]:
    seen: set[str] = set()
    mentions: list[str] = []
    for match in _DATE_PATTERN.findall(text or ""):
        value = match.strip()
        key = value.lower()
        if key not in seen:
            seen.add(key)
            mentions.append(value)
    return mentions


def _entity_terms(text: str) -> list[str]:
    # Lightweight fallback: proper English words, quoted phrases, and durable query terms.
    entities: list[str] = []
    seen: set[str] = set()
    for quoted in re.findall(r"['\"]([^'\"]{2,80})['\"]", text or ""):
        key = quoted.lower()
        if key not in seen:
            seen.add(key)
            entities.append(quoted)
    for match in re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b", text or ""):
        key = match.lower()
        if key not in seen:
            seen.add(key)
            entities.append(match)
    for term in _query_terms(text):
        if term not in seen and len(term) >= 3:
            seen.add(term)
            entities.append(term)
    return entities[:32]


def _overlap_score(query_values: list[str], candidate_values: list[str]) -> float:
    if not query_values or not candidate_values:
        return 0.0
    q = {v.lower() for v in query_values}
    c = {v.lower() for v in candidate_values}
    return len(q & c) / max(len(q), 1)


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + max(rank, 1))


def _evidence_from_row(row: aiosqlite.Row) -> dict[str, object]:
    return {
        "evidence_id": row["evidence_id"],
        "conversation_id": row["conversation_id"],
        "user_id": row["user_id"],
        "turn_id": row["turn_id"],
        "speaker": row["speaker"],
        "content": row["content"],
        "normalized_content": row["normalized_content"],
        "timestamp": row["timestamp"],
        "conversation_date": row["conversation_date"],
        "entities": _json_loads(row["entities"], []),
        "date_mentions": _json_loads(row["date_mentions"], []),
        "source": row["source"],
        "metadata": _json_loads(row["metadata_json"], {}),
        "score": row["score"] if "score" in row.keys() else 0.0,
        "channels": _json_loads(row["channels"], []) if "channels" in row.keys() else [],
    }


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
        conversation_date=row["conversation_date"] if row["conversation_date"] else "",
        metadata=(
            json.loads(row["metadata_json"])
            if row["metadata_json"] and row["metadata_json"] != "{}"
            else {}
        ),
    )


class PersistentBeliefStore(IBeliefStore):
    def __init__(
        self,
        db_path: str | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        max_beliefs: int = 10000,
    ) -> None:
        self._db_path: str = db_path or get_settings().database.db_path
        self._embedding_service: EmbeddingService | None = embedding_service
        self._vector_store: VectorStore | None = vector_store
        self._conn: aiosqlite.Connection | None = None
        self._max_beliefs: int = max_beliefs

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._create_tables()
        return self._conn

    async def _create_tables(self) -> None:
        conn = self._conn

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
                conversation_date TEXT DEFAULT '',
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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_evidence (
                evidence_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                turn_id INTEGER NOT NULL DEFAULT 0,
                speaker TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                normalized_content TEXT NOT NULL DEFAULT '',
                timestamp INTEGER NOT NULL DEFAULT 0,
                conversation_date TEXT DEFAULT '',
                entities TEXT DEFAULT '[]',
                date_mentions TEXT DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'chat',
                metadata_json TEXT DEFAULT '{}',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_evidence_conversation
            ON memory_evidence(conversation_id, turn_id, timestamp);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_evidence_user
            ON memory_evidence(user_id, conversation_id, timestamp);
            """
        )

        await conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_evidence_fts USING fts5(
                content,
                content='memory_evidence',
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
        metadata = dict(belief.metadata or {})
        timestamp = belief.timestamp or now_ms
        should_create_evidence = self._should_create_evidence(belief)
        evidence_id = str(metadata.get("evidence_id") or f"E-{belief_id}")
        if should_create_evidence:
            metadata["evidence_id"] = evidence_id
            metadata.setdefault("evidence_ids", [evidence_id])
        elif not metadata.get("evidence_ids"):
            inferred = await self._infer_recent_evidence_ids(
                conversation_id=conversation_id,
                speaker=belief.source,
                timestamp=timestamp,
            )
            if inferred:
                metadata["evidence_ids"] = inferred
        belief.metadata = metadata

        row = await conn.execute(
            """
            INSERT INTO beliefs (
                id, conversation_id, user_id, content, source,
                confidence, base_confidence, last_accessed,
                memory_type, layer, entities, emotion,
                depends_on, child_belief_ids, superseded_by,
                status, is_composite, timestamp, conversation_date,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING rowid
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
                timestamp,
                belief.conversation_date,
                json.dumps(metadata, ensure_ascii=False),
                now_ms,
                now_ms,
            ),
        )
        inserted = await row.fetchone()
        inserted_rowid = inserted[0]

        await conn.execute(
            "INSERT INTO beliefs_fts(rowid, content) VALUES (?, ?);",
            (inserted_rowid, belief.content),
        )

        if should_create_evidence:
            turn_id = await self._next_evidence_turn_id(conversation_id)
            await self._insert_evidence_row(
                conn=conn,
                evidence_id=evidence_id,
                conversation_id=conversation_id,
                user_id=user_id,
                turn_id=turn_id,
                speaker=belief.source,
                content=belief.content,
                timestamp=timestamp,
                conversation_date=belief.conversation_date,
                source="chat",
                metadata={
                    "belief_id": belief_id,
                    "memory_type": belief.memory_type,
                    **{k: v for k, v in metadata.items() if k != "evidence_ids"},
                },
                now_ms=now_ms,
            )

        await conn.commit()
        logger.debug("Belief added: %s -> %s", belief_id, belief.content[:60])

        await self._enforce_belief_cap()

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

        if should_create_evidence and self._embedding_service and self._vector_store:
            await self._embed_evidence(evidence_id, belief.content, conversation_id)

        return belief_id

    def _should_create_evidence(self, belief: Belief) -> bool:
        if not belief.content.strip():
            return False
        if belief.metadata.get("skip_evidence"):
            return False
        if belief.memory_type != "chat":
            return False
        return belief.source in {"user", "assistant", "system", "tool"}

    async def _next_evidence_turn_id(self, conversation_id: str) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT COALESCE(MAX(turn_id), 0) + 1 AS next_turn FROM memory_evidence "
            "WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return int(row["next_turn"] if row else 1)

    async def _infer_recent_evidence_ids(
        self,
        conversation_id: str,
        speaker: str,
        timestamp: int,
        limit: int = 2,
    ) -> list[str]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT evidence_id
            FROM memory_evidence
            WHERE conversation_id = ?
              AND speaker = ?
              AND timestamp <= ?
            ORDER BY timestamp DESC, turn_id DESC
            LIMIT ?
            """,
            (conversation_id, speaker, timestamp + 1000, limit),
        )
        rows = await cursor.fetchall()
        return [row["evidence_id"] for row in rows]

    async def _insert_evidence_row(
        self,
        conn: aiosqlite.Connection,
        evidence_id: str,
        conversation_id: str,
        user_id: str,
        turn_id: int,
        speaker: str,
        content: str,
        timestamp: int,
        conversation_date: str,
        source: str,
        metadata: dict[str, object] | None,
        now_ms: int,
    ) -> None:
        normalized = " ".join(content.split())
        entities = _entity_terms(content)
        dates = _date_mentions(content)
        row = await conn.execute(
            """
            INSERT OR IGNORE INTO memory_evidence (
                evidence_id, conversation_id, user_id, turn_id, speaker,
                content, normalized_content, timestamp, conversation_date,
                entities, date_mentions, source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING rowid
            """,
            (
                evidence_id,
                conversation_id,
                user_id,
                turn_id,
                speaker,
                content,
                normalized,
                timestamp,
                conversation_date,
                json.dumps(entities, ensure_ascii=False),
                json.dumps(dates, ensure_ascii=False),
                source,
                json.dumps(metadata or {}, ensure_ascii=False),
                now_ms,
                now_ms,
            ),
        )
        inserted = await row.fetchone()
        if inserted is None:
            return
        await conn.execute(
            "INSERT INTO memory_evidence_fts(rowid, content) VALUES (?, ?);",
            (inserted[0], normalized or content),
        )

    async def _embed_evidence(
        self,
        evidence_id: str,
        content: str,
        conversation_id: str,
    ) -> None:
        if not self._embedding_service or not self._vector_store:
            return
        try:
            vector = await self._embedding_service.embed(content)
            if vector is not None:
                await self._vector_store.add(
                    f"{_EVIDENCE_VECTOR_PREFIX}{evidence_id}",
                    vector,
                    metadata={"kind": "evidence", "conversation_id": conversation_id},
                )
        except Exception:
            logger.warning("evidence_embedding_skipped evidence_id=%s", evidence_id, exc_info=True)

    async def add_evidence(
        self,
        conversation_id: str,
        content: str,
        speaker: str = "user",
        user_id: str = "anonymous",
        evidence_id: str | None = None,
        turn_id: int | None = None,
        timestamp: int | None = None,
        conversation_date: str = "",
        source: str = "chat",
        metadata: dict[str, object] | None = None,
    ) -> str:
        conn = await self._get_conn()
        now_ms = current_time_ms()
        final_id = evidence_id or f"E-{uuid.uuid4()}"
        final_turn = turn_id if turn_id is not None else await self._next_evidence_turn_id(conversation_id)
        final_ts = timestamp if timestamp is not None else now_ms
        await self._insert_evidence_row(
            conn=conn,
            evidence_id=final_id,
            conversation_id=conversation_id,
            user_id=user_id,
            turn_id=final_turn,
            speaker=speaker,
            content=content,
            timestamp=final_ts,
            conversation_date=conversation_date,
            source=source,
            metadata=metadata,
            now_ms=now_ms,
        )
        await conn.commit()
        await self._embed_evidence(final_id, content, conversation_id)
        return final_id

    async def get(self, conversation_id: str, limit: int = 50) -> list[Belief]:
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
                conversation_date = ?,
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
                belief.conversation_date,
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
        cursor = await conn.execute(
            "SELECT rowid FROM memory_evidence WHERE conversation_id = ?",
            (conversation_id,),
        )
        evidence_rows = await cursor.fetchall()
        for row in evidence_rows:
            await conn.execute(
                "INSERT INTO memory_evidence_fts(memory_evidence_fts, rowid, content) "
                "VALUES('delete', ?, '');",
                (row["rowid"],),
            )
        await conn.execute(
            "DELETE FROM memory_evidence WHERE conversation_id = ?",
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
                    vector_results = await self._vector_store.search(query_vector, top_k)
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
        fts_query = _tokenize_fts_query(sanitized)
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
                (fts_query, min_confidence, top_k),
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

    async def retrieve_evidence_belief_context(
        self,
        conversation_id: str,
        query: str,
        max_tokens: int = 4000,
        rescue: bool = False,
    ) -> dict[str, object]:
        """Retrieve a compact Evidence-Belief Lattice context for one query.

        This is intentionally additive to IBeliefStore: callers that know about
        EBL can use it, while older readers still call get()/search_similar().
        """
        sanitized = query.strip()
        if not sanitized:
            return {
                "beliefs": [],
                "evidence": [],
                "context": "",
                "diagnostics": {
                    "retrieval_stage": "rescue" if rescue else "initial",
                    "retrieval_channels_hit": [],
                    "retrieved_belief_count": 0,
                    "retrieved_evidence_count": 0,
                    "linked_evidence_count": 0,
                    "unknown_rescued": False,
                    "evidence_coverage_score": 0.0,
                },
            }

        cfg = get_settings().memory
        if not cfg.ebl_enabled:
            return {
                "beliefs": [],
                "evidence": [],
                "context": "",
                "diagnostics": {
                    "retrieval_stage": "disabled",
                    "retrieval_channels_hit": [],
                    "retrieved_belief_count": 0,
                    "retrieved_evidence_count": 0,
                    "linked_evidence_count": 0,
                    "unknown_rescued": False,
                    "evidence_coverage_score": 0.0,
                },
            }

        multiplier = max(1, cfg.ebl_rescue_multiplier) if rescue else 1
        top_beliefs = max(1, cfg.ebl_belief_top_k) * multiplier
        top_evidence = max(1, cfg.ebl_evidence_top_k) * multiplier

        belief_hits: dict[str, dict[str, object]] = {}
        evidence_hits: dict[str, dict[str, object]] = {}

        def add_belief(belief: Belief, score: float, channel: str) -> None:
            hit = belief_hits.setdefault(
                belief.id,
                {"belief": belief, "score": 0.0, "channels": set()},
            )
            hit["score"] = float(hit["score"]) + score
            hit["channels"].add(channel)

        def add_evidence(evidence: dict[str, object], score: float, channel: str) -> None:
            evidence_id = str(evidence["evidence_id"])
            hit = evidence_hits.setdefault(
                evidence_id,
                {"evidence": evidence, "score": 0.0, "channels": set()},
            )
            hit["score"] = float(hit["score"]) + score
            hit["channels"].add(channel)

        # Belief semantic/keyword retrieval. search_similar already falls back
        # from vectors to FTS/LIKE, so it is treated as the belief-semantic lane.
        for rank, (belief, score) in enumerate(
            await self.search_similar(sanitized, top_k=top_beliefs, min_confidence=0.1),
            start=1,
        ):
            add_belief(
                belief,
                _rrf(rank) + score * cfg.ebl_belief_vector_weight,
                "belief_vector",
            )

        for rank, (belief, score) in enumerate(
            await self._search_beliefs_fts(conversation_id, sanitized, top_beliefs),
            start=1,
        ):
            add_belief(
                belief,
                _rrf(rank) + score * cfg.ebl_belief_keyword_weight,
                "belief_keyword",
            )

        for rank, evidence in enumerate(
            await self._search_evidence_vector(conversation_id, sanitized, top_evidence),
            start=1,
        ):
            add_evidence(
                evidence,
                _rrf(rank)
                + float(evidence.get("score", 0.0)) * cfg.ebl_evidence_vector_weight,
                "evidence_vector",
            )

        for rank, evidence in enumerate(
            await self._search_evidence_fts(conversation_id, sanitized, top_evidence),
            start=1,
        ):
            add_evidence(
                evidence,
                _rrf(rank)
                + float(evidence.get("score", 0.0)) * cfg.ebl_evidence_keyword_weight,
                "evidence_keyword",
            )

        query_terms = _query_terms(sanitized)
        query_dates = _date_mentions(sanitized)
        query_entities = _entity_terms(sanitized)

        for belief, score, channel in await self._overlap_beliefs(
            conversation_id, query_terms, query_entities, query_dates, limit=top_beliefs
        ):
            add_belief(belief, score, channel)

        for evidence, score, channel in await self._overlap_evidence(
            conversation_id, query_terms, query_entities, query_dates, limit=top_evidence
        ):
            add_evidence(evidence, score, channel)

        linked_evidence_ids: set[str] = set()
        for hit in sorted(belief_hits.values(), key=lambda item: float(item["score"]), reverse=True)[:top_beliefs]:
            belief = hit["belief"]
            assert isinstance(belief, Belief)
            for evidence_id in self._belief_evidence_ids(belief):
                evidence = await self.get_evidence_by_id(evidence_id)
                if evidence is not None and evidence["conversation_id"] == conversation_id:
                    linked_evidence_ids.add(evidence_id)
                    add_evidence(evidence, cfg.ebl_linked_evidence_weight, "linked_evidence")

        for evidence_id in list(evidence_hits.keys())[:top_evidence]:
            evidence = evidence_hits[evidence_id]["evidence"]
            for neighbor in await self._neighbor_evidence(evidence):
                add_evidence(neighbor, cfg.ebl_temporal_neighbor_weight, "temporal_neighbor")

        belief_items = []
        for hit in belief_hits.values():
            belief = hit["belief"]
            assert isinstance(belief, Belief)
            channels = sorted(hit["channels"])
            belief_items.append(
                {
                    "id": belief.id,
                    "content": belief.content,
                    "memory_type": belief.memory_type,
                    "layer": belief.layer,
                    "status": belief.status,
                    "confidence": belief.confidence,
                    "entities": belief.entities,
                    "conversation_date": belief.conversation_date,
                    "evidence_ids": self._belief_evidence_ids(belief),
                    "score": round(float(hit["score"]), 4),
                    "channels": channels,
                }
            )

        evidence_items = []
        for hit in evidence_hits.values():
            evidence = dict(hit["evidence"])
            channels = sorted(hit["channels"])
            evidence["score"] = round(float(hit["score"]), 4)
            evidence["channels"] = channels
            evidence_items.append(evidence)

        belief_items.sort(key=lambda item: float(item["score"]), reverse=True)
        evidence_items.sort(key=lambda item: float(item["score"]), reverse=True)

        belief_items = belief_items[: min(top_beliefs, 16)]
        evidence_items = evidence_items[: min(top_evidence, 24)]

        context = self._format_ebl_context(belief_items, evidence_items, max_tokens=max_tokens)
        channels_hit = sorted(
            {
                channel
                for item in belief_items + evidence_items
                for channel in item.get("channels", [])
            }
        )
        coverage = min(1.0, len(evidence_items) / 3.0)
        diagnostics = {
            "retrieval_stage": "rescue" if rescue else "initial",
            "retrieval_channels_hit": channels_hit,
            "retrieved_belief_count": len(belief_items),
            "retrieved_evidence_count": len(evidence_items),
            "linked_evidence_count": len(linked_evidence_ids),
            "unknown_rescued": rescue and bool(evidence_items),
            "evidence_coverage_score": round(coverage, 4),
        }
        return {
            "beliefs": belief_items,
            "evidence": evidence_items,
            "context": context,
            "diagnostics": diagnostics,
        }

    async def get_evidence_by_id(self, evidence_id: str) -> dict[str, object] | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM memory_evidence WHERE evidence_id = ?",
            (evidence_id,),
        )
        row = await cursor.fetchone()
        return _evidence_from_row(row) if row else None

    async def get_evidence_by_ids(self, evidence_ids: list[str]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for evidence_id in evidence_ids:
            evidence = await self.get_evidence_by_id(evidence_id)
            if evidence is not None:
                result.append(evidence)
        return result

    def _belief_evidence_ids(self, belief: Belief) -> list[str]:
        raw = belief.metadata.get("evidence_ids") or belief.metadata.get("evidence_id") or []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw if item]
        return []

    async def _search_beliefs_fts(
        self,
        conversation_id: str,
        query: str,
        top_k: int,
    ) -> list[tuple[Belief, float]]:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """
                SELECT b.*, rank
                FROM beliefs_fts
                JOIN beliefs b ON b.rowid = beliefs_fts.rowid
                WHERE beliefs_fts MATCH ?
                  AND b.conversation_id = ?
                  AND b.status = 'active'
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_match_query(query), conversation_id, top_k),
            )
            rows = await cursor.fetchall()
        except aiosqlite.OperationalError:
            rows = []
        results: list[tuple[Belief, float]] = []
        for row in rows:
            rank = row["rank"] if "rank" in row.keys() else 0.0
            results.append((_belief_from_row(row), max(0.0, min(1.0, 1.0 / (1.0 + abs(rank))))))
        if results:
            return results
        terms = _query_terms(query)
        if not terms:
            return []
        like = f"%{terms[0]}%"
        cursor = await conn.execute(
            """
            SELECT * FROM beliefs
            WHERE conversation_id = ?
              AND status = 'active'
              AND content LIKE ?
            ORDER BY confidence DESC, timestamp DESC
            LIMIT ?
            """,
            (conversation_id, like, top_k),
        )
        return [(_belief_from_row(row), 0.35) for row in await cursor.fetchall()]

    async def _search_evidence_fts(
        self,
        conversation_id: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, object]]:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """
                SELECT e.*, rank
                FROM memory_evidence_fts
                JOIN memory_evidence e ON e.rowid = memory_evidence_fts.rowid
                WHERE memory_evidence_fts MATCH ?
                  AND e.conversation_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_match_query(query), conversation_id, top_k),
            )
            rows = await cursor.fetchall()
        except aiosqlite.OperationalError:
            rows = []
        results: list[dict[str, object]] = []
        for row in rows:
            evidence = _evidence_from_row(row)
            rank = row["rank"] if "rank" in row.keys() else 0.0
            evidence["score"] = max(0.0, min(1.0, 1.0 / (1.0 + abs(rank))))
            results.append(evidence)
        if results:
            return results
        terms = _query_terms(query)
        if not terms:
            return []
        cursor = await conn.execute(
            """
            SELECT * FROM memory_evidence
            WHERE conversation_id = ?
              AND content LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (conversation_id, f"%{terms[0]}%", top_k),
        )
        fallback = []
        for row in await cursor.fetchall():
            evidence = _evidence_from_row(row)
            evidence["score"] = 0.35
            fallback.append(evidence)
        return fallback

    async def _search_evidence_vector(
        self,
        conversation_id: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, object]]:
        if not self._embedding_service or not self._vector_store:
            return []
        try:
            query_vector = await self._embedding_service.embed(query)
            if query_vector is None:
                return []
            vector_results = await self._vector_store.search(query_vector, top_k=max(top_k * 5, 50))
        except Exception:
            logger.warning("evidence_vector_search_failed", exc_info=True)
            return []
        results: list[dict[str, object]] = []
        for vector_id, score in vector_results:
            if not vector_id.startswith(_EVIDENCE_VECTOR_PREFIX):
                continue
            evidence_id = vector_id[len(_EVIDENCE_VECTOR_PREFIX):]
            evidence = await self.get_evidence_by_id(evidence_id)
            if evidence is None or evidence["conversation_id"] != conversation_id:
                continue
            evidence["score"] = score
            results.append(evidence)
            if len(results) >= top_k:
                break
        return results

    async def _overlap_beliefs(
        self,
        conversation_id: str,
        query_terms: list[str],
        query_entities: list[str],
        query_dates: list[str],
        limit: int,
    ) -> list[tuple[Belief, float, str]]:
        cfg = get_settings().memory
        beliefs = await self.get(conversation_id, limit=400)
        scored: list[tuple[Belief, float, str]] = []
        for belief in beliefs:
            content_terms = _query_terms(belief.content)
            content_dates = _date_mentions(belief.content) + list(
                belief.metadata.get("date_mentions", [])
                if isinstance(belief.metadata.get("date_mentions"), list)
                else []
            )
            entity_score = _overlap_score(query_entities or query_terms, belief.entities + content_terms)
            date_score = _overlap_score(query_dates, content_dates)
            term_score = _overlap_score(query_terms, content_terms)
            score = (
                cfg.ebl_belief_entity_overlap_weight * entity_score
                + cfg.ebl_belief_date_overlap_weight * date_score
                + cfg.ebl_belief_term_overlap_weight * term_score
            )
            if score > 0:
                channel = "date_overlap" if date_score >= max(entity_score, term_score) else "entity_overlap"
                scored.append((belief, score, channel))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def _overlap_evidence(
        self,
        conversation_id: str,
        query_terms: list[str],
        query_entities: list[str],
        query_dates: list[str],
        limit: int,
    ) -> list[tuple[dict[str, object], float, str]]:
        cfg = get_settings().memory
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT * FROM memory_evidence
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT 500
            """,
            (conversation_id,),
        )
        scored: list[tuple[dict[str, object], float, str]] = []
        for row in await cursor.fetchall():
            evidence = _evidence_from_row(row)
            content = str(evidence["content"])
            content_terms = _query_terms(content)
            entities = list(evidence.get("entities", [])) + content_terms
            dates = list(evidence.get("date_mentions", [])) + _date_mentions(content)
            entity_score = _overlap_score(query_entities or query_terms, entities)
            date_score = _overlap_score(query_dates, dates)
            term_score = _overlap_score(query_terms, content_terms)
            score = (
                cfg.ebl_evidence_entity_overlap_weight * entity_score
                + cfg.ebl_evidence_date_overlap_weight * date_score
                + cfg.ebl_evidence_term_overlap_weight * term_score
            )
            if score > 0:
                channel = "date_overlap" if date_score >= max(entity_score, term_score) else "entity_overlap"
                scored.append((evidence, score, channel))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def _neighbor_evidence(self, evidence: dict[str, object]) -> list[dict[str, object]]:
        conn = await self._get_conn()
        turn_id = int(evidence.get("turn_id") or 0)
        window = max(1, get_settings().memory.ebl_neighbor_turn_window)
        cursor = await conn.execute(
            """
            SELECT * FROM memory_evidence
            WHERE conversation_id = ?
              AND turn_id BETWEEN ? AND ?
              AND evidence_id != ?
            ORDER BY turn_id ASC
            LIMIT 4
            """,
            (
                evidence["conversation_id"],
                max(0, turn_id - window),
                turn_id + window,
                evidence["evidence_id"],
            ),
        )
        return [_evidence_from_row(row) for row in await cursor.fetchall()]

    def _format_ebl_context(
        self,
        beliefs: list[dict[str, object]],
        evidence: list[dict[str, object]],
        max_tokens: int,
    ) -> str:
        lines: list[str] = [
            "Use this Evidence-Belief Lattice for memory grounding.",
            "Prefer Evidence Ledger quotes for final factual answers; beliefs are navigation and synthesis only.",
            "If evidence is insufficient, say you do not know instead of guessing.",
            "",
            "Belief Lattice:",
        ]
        for belief in beliefs:
            evidence_ids = ",".join(str(item) for item in belief.get("evidence_ids", [])) or "none"
            lines.append(
                "- [{id}] L{layer}/{memory_type} status={status} conf={confidence:.2f} "
                "evidence={evidence_ids} score={score}: {content}".format(
                    id=belief["id"],
                    layer=belief["layer"],
                    memory_type=belief["memory_type"],
                    status=belief["status"],
                    confidence=float(belief["confidence"]),
                    evidence_ids=evidence_ids,
                    score=belief["score"],
                    content=belief["content"],
                )
            )
        lines.append("")
        lines.append("Evidence Ledger:")
        for item in evidence:
            date = item.get("conversation_date") or item.get("timestamp") or ""
            lines.append(
                "- [{id}] turn={turn} speaker={speaker} date={date} score={score}: {content}".format(
                    id=item["evidence_id"],
                    turn=item["turn_id"],
                    speaker=item["speaker"],
                    date=date,
                    score=item["score"],
                    content=item["content"],
                )
            )
        budget_chars = max(1000, max_tokens * 4)
        text = "\n".join(lines)
        if len(text) <= budget_chars:
            return text
        return text[:budget_chars].rsplit("\n", 1)[0]

    async def get_similar_task_count(
        self,
        query: str,
        days: int = 7,
        similarity_threshold: float = 0.8,
    ) -> int:
        """获取最近 N 天内与查询相似的任务数量。

        Args:
            query: 查询文本
            days: 天数窗口
            similarity_threshold: 相似度阈值（向量相似度）

        Returns:
            int: 相似任务数量
        """
        sanitized = query.strip()
        if not sanitized:
            return 0

        conn = await self._get_conn()
        cutoff_ms = int((time.time() - days * 24 * 60 * 60) * 1000)

        # 首先尝试向量搜索
        if self._vector_store and self._embedding_service:
            try:
                query_vector = await self._embedding_service.embed(sanitized)
                if query_vector is not None:
                    # 获取所有相似度高于阈值的向量
                    vector_results = await self._vector_store.search(
                        query_vector,
                        top_k=100,  # 最多检查 100 个
                    )

                    count = 0
                    for belief_id, score in vector_results:
                        if score >= similarity_threshold:
                            # 检查时间戳
                            cursor = await conn.execute(
                                "SELECT timestamp, memory_type FROM beliefs WHERE id = ?",
                                (belief_id,),
                            )
                            row = await cursor.fetchone()
                            if (
                                row
                                and row["timestamp"] >= cutoff_ms
                                and row["memory_type"] == "task"
                            ):
                                count += 1

                    if count > 0:
                        return count
            except Exception:
                logger.warning(
                    "vector_count_failed, falling back to text search",
                    exc_info=True,
                )

        # 回退到文本搜索（使用 FTS5）
        fts_query = _tokenize_fts_query(sanitized)
        try:
            cursor = await conn.execute(
                """
                SELECT COUNT(DISTINCT b.id) as cnt
                FROM beliefs_fts fts
                JOIN beliefs b ON fts.rowid = b.rowid
                WHERE fts MATCH ?
                  AND b.status = 'active'
                  AND b.memory_type = 'task'
                  AND b.timestamp >= ?
                """,
                (fts_query, cutoff_ms),
            )
            row = await cursor.fetchone()
            if row:
                return row["cnt"] or 0
        except Exception:
            logger.exception("fts_count_failed")

        # 最简单的 LIKE 回退
        cursor = await conn.execute(
            """
            SELECT COUNT(DISTINCT id) as cnt
            FROM beliefs
            WHERE content LIKE ?
              AND status = 'active'
              AND memory_type = 'task'
              AND timestamp >= ?
            """,
            (f"%{sanitized}%", cutoff_ms),
        )
        row = await cursor.fetchone()
        return row["cnt"] or 0 if row else 0

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
        rows_raw = list(await cursor_obj.fetchall())
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
                    conversation_id,
                    user_id,
                    cursor_ts,
                    cursor_ts,
                    cursor_id,
                    effective_limit,
                ]
            else:
                params = [
                    conversation_id,
                    cursor_ts,
                    cursor_ts,
                    cursor_id,
                    effective_limit,
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
        rows_raw = list(await cursor_obj.fetchall())
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

    async def _enforce_belief_cap(self) -> None:
        """当信念总数超过 max_beliefs 时，淘汰最旧的信念。

        按 timestamp ASC 排序，删除超出部分中最旧的记录。
        """
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM beliefs WHERE status = 'active'")
        row = await cursor.fetchone()
        total = row["cnt"] if row else 0

        if total <= self._max_beliefs:
            return

        excess = total - self._max_beliefs

        cursor = await conn.execute(
            """
            SELECT id FROM beliefs
            WHERE status = 'active'
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (excess,),
        )
        rows = await cursor.fetchall()
        ids_to_delete = [r["id"] for r in rows]

        if not ids_to_delete:
            return

        placeholders = ",".join("?" for _ in ids_to_delete)
        await conn.execute(
            f"DELETE FROM beliefs WHERE id IN ({placeholders})", ids_to_delete
        )
        await conn.execute(
            "DELETE FROM beliefs_fts WHERE rowid IN ("
            "SELECT rowid FROM beliefs WHERE id IN ({})"
            ")".format(placeholders),
            ids_to_delete,
        )
        await conn.commit()
        logger.info("Evicted %d old beliefs to enforce max_beliefs=%d", len(ids_to_delete), self._max_beliefs)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

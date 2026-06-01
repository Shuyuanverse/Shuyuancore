# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from src.config import PersonaConfig, get_settings
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)


@dataclass
class DriftHistoryEntry:
    timestamp: int
    drift_score: float
    action: str
    dimension_scores: dict[str, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersonaAnchor:
    user_id: str
    anchor_type: str
    anchor_data: dict[str, Any]
    version: int
    is_active: bool
    created_at: int
    updated_at: int
    drift_history: list[DriftHistoryEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class PersonaMemory:
    def __init__(
        self,
        db_path: str | None = None,
        config: PersonaConfig | None = None,
    ) -> None:
        self._db_path: str = db_path or get_settings().database.db_path
        self._config: PersonaConfig = config or get_settings().persona
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
            CREATE TABLE IF NOT EXISTS persona_anchors (
                user_id TEXT NOT NULL,
                anchor_type TEXT NOT NULL,
                anchor_data_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                drift_history_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                PRIMARY KEY (user_id, anchor_type)
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_persona_anchors_user_id
            ON persona_anchors(user_id, is_active);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_persona_anchors_type
            ON persona_anchors(anchor_type, is_active);
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drift_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                anchor_type TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                drift_score REAL NOT NULL,
                action TEXT NOT NULL,
                dimension_scores_json TEXT,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (user_id, anchor_type) REFERENCES persona_anchors(user_id, anchor_type)
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drift_history_user_anchor
            ON drift_history(user_id, anchor_type, timestamp DESC);
            """
        )

        await conn.commit()

    async def get_anchor(
        self,
        user_id: str,
        anchor_type: str,
    ) -> PersonaAnchor | None:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT * FROM persona_anchors
            WHERE user_id = ? AND anchor_type = ?
            """,
            (user_id, anchor_type),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        return self._row_to_anchor(row)

    async def create_anchor(
        self,
        user_id: str,
        anchor_type: str,
        anchor_data: dict[str, Any],
        version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> PersonaAnchor:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            INSERT OR REPLACE INTO persona_anchors
                (user_id, anchor_type, anchor_data_json, version, is_active,
                 created_at, updated_at, drift_history_json, metadata_json)
            VALUES (?, ?, ?, ?, 1, ?, ?, '[]', ?)
            """,
            (
                user_id,
                anchor_type,
                json.dumps(anchor_data, ensure_ascii=False),
                version,
                now_ms,
                now_ms,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

        await conn.commit()

        return PersonaAnchor(
            user_id=user_id,
            anchor_type=anchor_type,
            anchor_data=anchor_data,
            version=version,
            is_active=True,
            created_at=now_ms,
            updated_at=now_ms,
            drift_history=[],
            metadata=metadata or {},
        )

    async def update_anchor(
        self,
        user_id: str,
        anchor_type: str,
        anchor_data: dict[str, Any] | None = None,
        increment_version: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> PersonaAnchor | None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        existing = await self.get_anchor(user_id, anchor_type)
        if existing is None:
            return None

        update_fields = []
        params: list[Any] = []

        if anchor_data is not None:
            update_fields.append("anchor_data_json = ?")
            params.append(json.dumps(anchor_data, ensure_ascii=False))

        if increment_version:
            update_fields.append("version = version + 1")

        if metadata is not None:
            update_fields.append("metadata_json = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))

        update_fields.append("updated_at = ?")
        params.append(now_ms)

        params.append(user_id)
        params.append(anchor_type)

        await conn.execute(
            f"""
            UPDATE persona_anchors
            SET {", ".join(update_fields)}
            WHERE user_id = ? AND anchor_type = ?
            """,
            params,
        )

        await conn.commit()
        return await self.get_anchor(user_id, anchor_type)

    async def record_drift(
        self,
        user_id: str,
        anchor_type: str,
        drift_score: float,
        action: str,
        dimension_scores: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        anchor = await self.get_anchor(user_id, anchor_type)
        if anchor is None:
            anchor = await self.create_anchor(
                user_id=user_id,
                anchor_type=anchor_type,
                anchor_data={},
            )

        await conn.execute(
            """
            INSERT INTO drift_history
                (user_id, anchor_type, timestamp, drift_score, action,
                 dimension_scores_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                anchor_type,
                now_ms,
                drift_score,
                action,
                json.dumps(dimension_scores, ensure_ascii=False) if dimension_scores else None,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

        await conn.execute(
            """
            UPDATE persona_anchors
            SET updated_at = ?
            WHERE user_id = ? AND anchor_type = ?
            """,
            (now_ms, user_id, anchor_type),
        )

        await conn.commit()
        logger.info(
            "Recorded drift for user %s (type=%s, score=%.3f, action=%s)",
            user_id,
            anchor_type,
            drift_score,
            action,
        )

    async def get_drift_history(
        self,
        user_id: str,
        anchor_type: str,
        limit: int | None = None,
    ) -> list[DriftHistoryEntry]:
        conn = await self._get_conn()

        anchor = await self.get_anchor(user_id, anchor_type)
        if anchor is None:
            return []

        if limit is not None:
            cursor = await conn.execute(
                """
                SELECT timestamp, drift_score, action,
                       dimension_scores_json, metadata_json
                FROM drift_history
                WHERE user_id = ? AND anchor_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, anchor_type, limit),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT timestamp, drift_score, action,
                       dimension_scores_json, metadata_json
                FROM drift_history
                WHERE user_id = ? AND anchor_type = ?
                ORDER BY timestamp ASC
                """,
                (user_id, anchor_type),
            )

        rows = await cursor.fetchall()
        if not rows:
            return []

        entries = [
            DriftHistoryEntry(
                timestamp=row[0],
                drift_score=row[1],
                action=row[2],
                dimension_scores=(
                    json.loads(row[3]) if row[3] and row[3] != "null" else None
                ),
                metadata=json.loads(row[4]) if row[4] else {},
            )
            for row in rows
        ]

        if limit is not None:
            entries.reverse()

        return entries

    async def get_drift_statistics(
        self,
        user_id: str,
        anchor_type: str,
    ) -> dict[str, Any]:
        drift_history = await self.get_drift_history(user_id, anchor_type)

        if not drift_history:
            return {
                "total_records": 0,
                "avg_drift_score": 0.0,
                "max_drift_score": 0.0,
                "min_drift_score": 0.0,
                "drift_trend": "stable",
            }

        scores = [entry.drift_score for entry in drift_history]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)

        if len(scores) >= 2:
            recent_avg = sum(scores[-5:]) / min(5, len(scores))
            older_avg = (
                sum(scores[:-5]) / max(1, len(scores) - 5) if len(scores) > 5 else recent_avg
            )

            if recent_avg > older_avg + 0.05:
                trend = "increasing"
            elif recent_avg < older_avg - 0.05:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        action_counts: dict[str, int] = {}
        for entry in drift_history:
            action_counts[entry.action] = action_counts.get(entry.action, 0) + 1

        return {
            "total_records": len(drift_history),
            "avg_drift_score": round(avg_score, 4),
            "max_drift_score": round(max_score, 4),
            "min_drift_score": round(min_score, 4),
            "drift_trend": trend,
            "action_distribution": action_counts,
        }

    async def deactivate_anchor(
        self,
        user_id: str,
        anchor_type: str,
    ) -> bool:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        cursor = await conn.execute(
            """
            UPDATE persona_anchors
            SET is_active = 0, updated_at = ?
            WHERE user_id = ? AND anchor_type = ?
            """,
            (now_ms, user_id, anchor_type),
        )

        affected = cursor.rowcount
        await conn.commit()

        if affected > 0:
            logger.info("Deactivated anchor: user=%s, type=%s", user_id, anchor_type)
            return True
        return False

    async def list_anchors(
        self,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[PersonaAnchor]:
        conn = await self._get_conn()

        active_filter = "" if include_inactive else "WHERE is_active = 1"

        cursor = await conn.execute(
            f"""
            SELECT * FROM persona_anchors
            {active_filter}
            WHERE user_id = ?
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

        return [self._row_to_anchor(row) for row in rows]

    async def delete_anchor(
        self,
        user_id: str,
        anchor_type: str,
    ) -> bool:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            DELETE FROM persona_anchors
            WHERE user_id = ? AND anchor_type = ?
            """,
            (user_id, anchor_type),
        )

        affected = cursor.rowcount
        await conn.commit()

        if affected > 0:
            logger.info("Deleted anchor: user=%s, type=%s", user_id, anchor_type)
            return True
        return False

    def _row_to_anchor(self, row: aiosqlite.Row) -> PersonaAnchor:
        drift_history_data = (
            json.loads(row["drift_history_json"]) if row["drift_history_json"] else []
        )
        drift_history = [
            DriftHistoryEntry(
                timestamp=entry["timestamp"],
                drift_score=entry["drift_score"],
                action=entry["action"],
                dimension_scores=entry.get("dimension_scores"),
                metadata=entry.get("metadata", {}),
            )
            for entry in drift_history_data
        ]

        return PersonaAnchor(
            user_id=row["user_id"],
            anchor_type=row["anchor_type"],
            anchor_data=json.loads(row["anchor_data_json"]) if row["anchor_data_json"] else {},
            version=row["version"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            drift_history=drift_history,
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

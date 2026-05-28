from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    timestamp: float
    user_id: str
    action: str
    resource: str
    params: dict[str, Any]
    result: str
    approved: bool | None
    approval_id: str
    duration_ms: float
    ip_address: str = ""
    error: str = ""


class AuditLogger:

    def __init__(self, db_path: str = "data/state.db") -> None:
        self._db_path: str = db_path
        self._cache: list[AuditEntry] = []
        self._conn: aiosqlite.Connection | None = None
        self._max_entries: int = 10000

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._ensure_table()
        return self._conn

    async def _ensure_table(self) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL DEFAULT '',
                params_json TEXT NOT NULL DEFAULT '{}',
                result TEXT NOT NULL DEFAULT 'success',
                approved INTEGER,
                approval_id TEXT NOT NULL DEFAULT '',
                duration_ms REAL NOT NULL DEFAULT 0.0,
                ip_address TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL
            )
            """
        )
        await conn.commit()

    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        params: dict[str, Any],
        result: str = "success",
        approved: bool | None = None,
        approval_id: str = "",
        duration_ms: float = 0.0,
        ip_address: str = "",
        error: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            resource=resource,
            params=_sanitize_params(params),
            result=result,
            approved=approved,
            approval_id=approval_id,
            duration_ms=duration_ms,
            ip_address=ip_address,
            error=error,
        )
        self._cache.append(entry)
        logger.info(
            "audit: %s %s on %s -> %s (%.1fms)",
            user_id,
            action,
            resource,
            result,
            duration_ms,
        )
        if len(self._cache) > self._max_entries:
            self._cache = self._cache[-self._max_entries // 2:]

    async def log_async(
        self,
        user_id: str,
        action: str,
        resource: str,
        params: dict[str, Any],
        result: str = "success",
        approved: bool | None = None,
        approval_id: str = "",
        duration_ms: float = 0.0,
        ip_address: str = "",
        error: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            resource=resource,
            params=_sanitize_params(params),
            result=result,
            approved=approved,
            approval_id=approval_id,
            duration_ms=duration_ms,
            ip_address=ip_address,
            error=error,
        )
        self._cache.append(entry)
        logger.info(
            "audit: %s %s on %s -> %s (%.1fms)",
            user_id,
            action,
            resource,
            result,
            duration_ms,
        )
        await self._flush_entry(entry)

    async def _flush_entry(self, entry: AuditEntry) -> None:
        try:
            conn = await self._get_conn()
            await conn.execute(
                """
                INSERT INTO audit_logs
                    (user_id, action, resource, params_json, result,
                     approved, approval_id, duration_ms, ip_address, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.user_id,
                    entry.action,
                    entry.resource,
                    json.dumps(entry.params, ensure_ascii=False),
                    entry.result,
                    entry.approved,
                    entry.approval_id,
                    entry.duration_ms,
                    entry.ip_address,
                    entry.error,
                    entry.timestamp,
                ),
            )
            await conn.commit()
        except Exception:
            logger.exception("Failed to flush audit entry to DB")

    async def flush_all(self) -> None:
        entries = self._cache[:]
        self._cache.clear()
        for entry in entries:
            await self._flush_entry(entry)

    def get_entries(
        self,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        entries = self._cache
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if action:
            entries = [e for e in entries if e.action == action]
        return [asdict(e) for e in entries[-limit:]]

    async def query_db(
        self,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        parts: list[str] = ["SELECT * FROM audit_logs WHERE 1=1"]
        params: list[Any] = []
        if user_id:
            parts.append("AND user_id = ?")
            params.append(user_id)
        if action:
            parts.append("AND action = ?")
            params.append(action)
        parts.append("ORDER BY timestamp DESC LIMIT ?")
        params.append(limit)
        cursor = await conn.execute(" ".join(parts), params)
        rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            d: dict[str, Any] = dict(row)
            d["params"] = json.loads(d.pop("params_json", "{}"))
            result.append(d)
        return result


_SENSITIVE_KEYS = {
    "api_key", "token", "password", "secret", "cookie", "authorization"
}


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_params(value)
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:200] + "...[truncated]"
        else:
            sanitized[key] = value
    return sanitized


_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    return _audit_logger

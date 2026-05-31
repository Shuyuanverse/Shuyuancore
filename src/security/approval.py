from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

_DB_PATH: str = "data/state.db"


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_name: str
    params: dict[str, Any]
    user_id: str
    created_at: float
    timeout: int
    status: str = "pending"
    approved: bool | None = None
    reason: str = ""
    resolved_by: str = ""
    resolved_at: float = 0.0
    stream_id: str | None = None
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class ApprovalManager:
    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path: str = db_path
        self._conn: aiosqlite.Connection | None = None
        self._events: dict[str, asyncio.Event] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._conn.commit()
        return self._conn

    async def initialize(self) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                params_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                approved INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                resolved_by TEXT NOT NULL DEFAULT '',
                timeout INTEGER NOT NULL DEFAULT 300,
                stream_id TEXT,
                created_at REAL NOT NULL,
                resolved_at REAL NOT NULL DEFAULT 0.0
            );
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_approvals_user_id ON approvals(user_id);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(user_id, status);"
        )
        await conn.commit()

        cursor = await conn.execute("SELECT * FROM approvals WHERE status = 'pending'")
        rows = await cursor.fetchall()
        async with self._lock:
            for row in rows:
                event = asyncio.Event()
                self._events[row["approval_id"]] = event

    async def request(
        self,
        tool_name: str,
        params: dict[str, Any],
        user_id: str,
        timeout: int = 300,
        approval_id: str | None = None,
        stream_id: str | None = None,
    ) -> ApprovalRequest:
        if approval_id is None:
            approval_id = f"{user_id}_{uuid.uuid4().hex[:12]}"

        event = asyncio.Event()
        async with self._lock:
            self._events[approval_id] = event

        now = time.time()
        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO approvals (
                approval_id, user_id, tool_name, params_json,
                status, timeout, stream_id, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                approval_id,
                user_id,
                tool_name,
                json.dumps(params, ensure_ascii=False),
                timeout,
                stream_id,
                now,
            ),
        )
        await conn.commit()

        return ApprovalRequest(
            approval_id=approval_id,
            tool_name=tool_name,
            params=params,
            user_id=user_id,
            created_at=now,
            timeout=timeout,
            stream_id=stream_id,
            _event=event,
        )

    async def resolve(
        self,
        approval_id: str,
        approved: bool,
        reason: str = "",
        resolved_by: str = "user",
    ) -> ApprovalRequest:
        now = time.time()
        new_status = "approved" if approved else "denied"

        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Approval {approval_id} not found")

        await conn.execute(
            """
            UPDATE approvals
            SET status = ?, approved = ?, reason = ?, resolved_by = ?, resolved_at = ?
            WHERE approval_id = ?
            """,
            (new_status, int(approved), reason, resolved_by, now, approval_id),
        )
        await conn.commit()

        async with self._lock:
            event = self._events.pop(approval_id, None)

        req = ApprovalRequest(
            approval_id=row["approval_id"],
            tool_name=row["tool_name"],
            params=json.loads(row["params_json"]) if row["params_json"] else {},
            user_id=row["user_id"],
            created_at=row["created_at"],
            timeout=row["timeout"],
            status=new_status,
            approved=approved,
            reason=reason,
            resolved_by=resolved_by,
            resolved_at=now,
            stream_id=row["stream_id"],
        )
        if event is not None:
            event.set()

        return req

    async def wait(self, approval_id: str, timeout: int | None = None) -> bool:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Approval {approval_id} not found")
        if row["status"] != "pending":
            return bool(row["approved"])

        async with self._lock:
            event = self._events.get(approval_id)
        if event is None:
            event = asyncio.Event()
            async with self._lock:
                self._events[approval_id] = event

        wait_timeout = timeout if timeout is not None else row["timeout"]
        try:
            await asyncio.wait_for(event.wait(), timeout=wait_timeout)
            cursor = await conn.execute(
                "SELECT approved FROM approvals WHERE approval_id = ?",
                (approval_id,),
            )
            row2 = await cursor.fetchone()
            if row2 is not None:
                return bool(row2["approved"])
            return False
        except asyncio.TimeoutError:
            cursor = await conn.execute(
                "SELECT status FROM approvals WHERE approval_id = ?",
                (approval_id,),
            )
            row3 = await cursor.fetchone()
            if row3 is not None and row3["status"] == "pending":
                await conn.execute(
                    """
                    UPDATE approvals
                    SET status = 'timeout', approved = 0,
                        reason = '审批超时自动拒绝', resolved_at = ?
                    WHERE approval_id = ?
                    """,
                    (time.time(), approval_id),
                )
                await conn.commit()
            async with self._lock:
                self._events.pop(approval_id, None)
            return False

    def get_request(self, approval_id: str) -> ApprovalRequest | None:
        return None

    async def aget_request(self, approval_id: str) -> ApprovalRequest | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        async with self._lock:
            event = self._events.get(approval_id, asyncio.Event())

        return ApprovalRequest(
            approval_id=row["approval_id"],
            tool_name=row["tool_name"],
            params=json.loads(row["params_json"]) if row["params_json"] else {},
            user_id=row["user_id"],
            created_at=row["created_at"],
            timeout=row["timeout"],
            status=row["status"],
            approved=(bool(row["approved"]) if row["approved"] is not None else None),
            reason=row["reason"],
            resolved_by=row["resolved_by"],
            resolved_at=row["resolved_at"],
            stream_id=row["stream_id"],
            _event=event,
        )

    async def list_pending_by_user(self, user_id: str) -> list[ApprovalRequest]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM approvals WHERE user_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()

        results: list[ApprovalRequest] = []
        for row in rows:
            async with self._lock:
                event = self._events.get(row["approval_id"], asyncio.Event())
            results.append(
                ApprovalRequest(
                    approval_id=row["approval_id"],
                    tool_name=row["tool_name"],
                    params=json.loads(row["params_json"]) if row["params_json"] else {},
                    user_id=row["user_id"],
                    created_at=row["created_at"],
                    timeout=row["timeout"],
                    status=row["status"],
                    stream_id=row["stream_id"],
                    _event=event,
                )
            )
        return results

    async def cleanup(self, max_age: int = 86400) -> int:
        conn = await self._get_conn()
        now = time.time()
        threshold = now - max_age
        cursor = await conn.execute(
            "SELECT approval_id FROM approvals WHERE created_at < ? AND status = 'pending'",
            (threshold,),
        )
        expired_rows = await cursor.fetchall()
        expired_ids = [row["approval_id"] for row in expired_rows]

        if expired_ids:
            placeholders = ",".join("?" for _ in expired_ids)
            await conn.execute(
                f"DELETE FROM approvals WHERE approval_id IN ({placeholders})",
                expired_ids,
            )
            await conn.commit()
            async with self._lock:
                for aid in expired_ids:
                    self._events.pop(aid, None)

        return len(expired_ids)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        async with self._lock:
            self._events.clear()


_managers: dict[str, ApprovalManager] = {}
_manager_lock = asyncio.Lock()


async def get_approval_manager(db_path: str | None = None) -> ApprovalManager:
    path = _DB_PATH if db_path is None else db_path
    async with _manager_lock:
        if path not in _managers:
            mgr = ApprovalManager(db_path=path)
            await mgr.initialize()
            _managers[path] = mgr
        return _managers[path]


def get_approval_manager_sync(db_path: str = _DB_PATH) -> ApprovalManager:
    return ApprovalManager(db_path=db_path)

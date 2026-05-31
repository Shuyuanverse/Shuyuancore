from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from src.security.audit import AuditLogger, get_audit_logger


class TestAuditLoggerBasics:

    async def test_log_creates_entry_in_cache(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_cache.db")
        logger = AuditLogger(db_path=db_path)
        logger.log(
            user_id="test_user",
            action="test_action",
            resource="test_resource",
            params={"key": "value"},
        )
        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0]["user_id"] == "test_user"
        assert entries[0]["action"] == "test_action"
        assert entries[0]["resource"] == "test_resource"
        assert entries[0]["params"]["key"] == "value"

    async def test_log_async_persists_to_db(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_audit.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log_async(
            user_id="user_a",
            action="cmd_exec",
            resource="terminal",
            params={"cmd": "ls"},
            result="success",
            duration_ms=12.5,
        )
        rows = await logger.query_db()
        assert len(rows) == 1
        assert rows[0]["user_id"] == "user_a"
        assert rows[0]["action"] == "cmd_exec"
        assert rows[0]["duration_ms"] == 12.5

    async def test_multiple_entries_persisted(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_multiple.db")
        logger = AuditLogger(db_path=db_path)
        for i in range(3):
            await logger.log_async(
                user_id=f"user_{i}",
                action="action",
                resource="resource",
                params={"i": i},
            )
        rows = await logger.query_db()
        assert len(rows) == 3

    async def test_query_db_filters_by_user(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_filter.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log_async(user_id="alice", action="read", resource="doc", params={})
        await logger.log_async(user_id="bob", action="write", resource="doc", params={})
        alice_rows = await logger.query_db(user_id="alice")
        assert len(alice_rows) == 1
        assert alice_rows[0]["user_id"] == "alice"

    async def test_query_db_filters_by_action(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_action.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log_async(user_id="u1", action="read", resource="r1", params={})
        await logger.log_async(user_id="u1", action="write", resource="r2", params={})
        read_rows = await logger.query_db(action="read")
        assert len(read_rows) == 1
        assert read_rows[0]["action"] == "read"

    async def test_sanitize_sensitive_params(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_sanitize.db")
        logger = AuditLogger(db_path=db_path)
        logger.log(
            user_id="u1",
            action="auth",
            resource="api",
            params={
                "api_key": "sk-1234567890",
                "token": "secret-token",
                "normal": "ok",
            },
        )
        entries = logger.get_entries()
        assert entries[0]["params"]["api_key"] == "***REDACTED***"
        assert entries[0]["params"]["token"] == "***REDACTED***"
        assert entries[0]["params"]["normal"] == "ok"


class TestAuditLoggerSingleton:

    def test_get_audit_logger_returns_same_instance(self) -> None:
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2


class TestAuditLoggerFlush:

    async def test_flush_all_persists_cache_to_db(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_flush.db")
        logger = AuditLogger(db_path=db_path)
        logger.log(user_id="u1", action="sync", resource="r1", params={})
        logger.log(user_id="u2", action="sync", resource="r2", params={})
        await logger.flush_all()
        rows = await logger.query_db()
        assert len(rows) == 2

    async def test_cache_cleared_after_flush(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_cache_clear.db")
        logger = AuditLogger(db_path=db_path)
        logger.log(user_id="u1", action="a", resource="r", params={})
        await logger.flush_all()
        assert len(logger.get_entries()) == 0


class TestAuditLoggerCleanup:

    async def test_connection_reused(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test_reuse.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log_async(user_id="u1", action="a", resource="r", params={})
        await logger.log_async(user_id="u2", action="b", resource="r", params={})
        rows = await logger.query_db()
        assert len(rows) == 2
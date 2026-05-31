from __future__ import annotations

import time

import aiosqlite
import pytest
from unittest.mock import AsyncMock

from src.models.interfaces import ChatResult
from src.skills.curator import run_curation


def _relative_ms(days_ago: int) -> int:
    return int(time.time() - days_ago * 86400) * 1000


@pytest.fixture
def mock_router():
    router = AsyncMock()
    router.chat = AsyncMock()
    return router


@pytest.mark.asyncio
async def test_llm_review_disabled_by_default(tmp_path, mock_router):
    db_path = str(tmp_path / "llm_default.db")
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, source TEXT NOT NULL DEFAULT 'manual', description TEXT,
            tags TEXT, preconditions TEXT,
            causality_level0 TEXT, causality_level1 TEXT, causality_level2 TEXT,
            boundaries TEXT, failure_modes TEXT, dependencies TEXT,
            version_history TEXT, status TEXT, is_pinned INTEGER,
            created_at INTEGER, updated_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT, emotion REAL,
            depends_on TEXT, child_belief_ids TEXT,
            superseded_by TEXT, status TEXT,
            is_composite INTEGER, timestamp INTEGER,
            metadata TEXT
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "test-skill", "skill", "b1", "manual", "a test skill",
            '["test"]', "[]", "does something", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "test", "skill", 0.8, 0.8, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path, router=mock_router)
    assert result["llm_reviewed"] == 0
    assert result["llm_demoted"] == 0
    mock_router.chat.assert_not_called()


@pytest.mark.asyncio
async def test_llm_review_promotes_good_skill(tmp_path, mock_router, monkeypatch):
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.skills, "llm_review_enabled", True)

    db_path = str(tmp_path / "llm_good.db")
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, source TEXT NOT NULL DEFAULT 'manual', description TEXT,
            tags TEXT, preconditions TEXT,
            causality_level0 TEXT, causality_level1 TEXT, causality_level2 TEXT,
            boundaries TEXT, failure_modes TEXT, dependencies TEXT,
            version_history TEXT, status TEXT, is_pinned INTEGER,
            created_at INTEGER, updated_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT, emotion REAL,
            depends_on TEXT, child_belief_ids TEXT,
            superseded_by TEXT, status TEXT,
            is_composite INTEGER, timestamp INTEGER,
            metadata TEXT
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "good-skill", "skill", "b1", "manual", "well-defined skill",
            '["api", "test"]', "[]", "processes API requests", "", "", '["no auth"]', "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "good", "skill", 0.8, 0.8, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    mock_router.chat.return_value = ChatResult(
        content='{"quality_score": 8, "issues": [], "suggested_action": "keep"}',
        tokens_used=50,
        model_used="test-model",
        finish_reason="stop",
    )

    result = await run_curation(db_path=db_path, router=mock_router)
    assert result["llm_reviewed"] == 1
    assert result["llm_demoted"] == 0
    mock_router.chat.assert_called_once()


@pytest.mark.asyncio
async def test_llm_review_demotes_bad_skill(tmp_path, mock_router, monkeypatch):
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.skills, "llm_review_enabled", True)

    db_path = str(tmp_path / "llm_bad.db")
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, source TEXT NOT NULL DEFAULT 'manual', description TEXT,
            tags TEXT, preconditions TEXT,
            causality_level0 TEXT, causality_level1 TEXT, causality_level2 TEXT,
            boundaries TEXT, failure_modes TEXT, dependencies TEXT,
            version_history TEXT, status TEXT, is_pinned INTEGER,
            created_at INTEGER, updated_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT, emotion REAL,
            depends_on TEXT, child_belief_ids TEXT,
            superseded_by TEXT, status TEXT,
            is_composite INTEGER, timestamp INTEGER,
            metadata TEXT
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "bad-skill", "skill", "b1", "manual", "",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "bad", "skill", 0.8, 0.8, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    mock_router.chat.return_value = ChatResult(
        content='{"quality_score": 2, "issues": ["no description", "no causality"], "suggested_action": "demote"}',
        tokens_used=50,
        model_used="test-model",
        finish_reason="stop",
    )

    result = await run_curation(db_path=db_path, router=mock_router)
    assert result["llm_reviewed"] == 1
    assert result["llm_demoted"] == 1

    conn2 = await aiosqlite.connect(db_path)
    cursor = await conn2.execute(
        "SELECT status FROM skill_nodes WHERE node_id = ?", ("n1",)
    )
    row = await cursor.fetchone()
    assert row[0] == "stale"
    await conn2.close()


@pytest.mark.asyncio
async def test_llm_review_skips_pinned(tmp_path, mock_router, monkeypatch):
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.skills, "llm_review_enabled", True)

    db_path = str(tmp_path / "llm_pinned.db")
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, source TEXT NOT NULL DEFAULT 'manual', description TEXT,
            tags TEXT, preconditions TEXT,
            causality_level0 TEXT, causality_level1 TEXT, causality_level2 TEXT,
            boundaries TEXT, failure_modes TEXT, dependencies TEXT,
            version_history TEXT, status TEXT, is_pinned INTEGER,
            created_at INTEGER, updated_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT, emotion REAL,
            depends_on TEXT, child_belief_ids TEXT,
            superseded_by TEXT, status TEXT,
            is_composite INTEGER, timestamp INTEGER,
            metadata TEXT
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "pinned-skill", "skill", "b1", "manual", "bad pinned skill",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 1, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "pinned", "skill", 0.8, 0.8, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path, router=mock_router)
    assert result["llm_reviewed"] == 0
    assert result["llm_demoted"] == 0
    mock_router.chat.assert_not_called()


@pytest.mark.asyncio
async def test_llm_review_handles_llm_failure(tmp_path, mock_router, monkeypatch):
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.skills, "llm_review_enabled", True)

    db_path = str(tmp_path / "llm_fail.db")
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, source TEXT NOT NULL DEFAULT 'manual', description TEXT,
            tags TEXT, preconditions TEXT,
            causality_level0 TEXT, causality_level1 TEXT, causality_level2 TEXT,
            boundaries TEXT, failure_modes TEXT, dependencies TEXT,
            version_history TEXT, status TEXT, is_pinned INTEGER,
            created_at INTEGER, updated_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT, emotion REAL,
            depends_on TEXT, child_belief_ids TEXT,
            superseded_by TEXT, status TEXT,
            is_composite INTEGER, timestamp INTEGER,
            metadata TEXT
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "failing-skill", "skill", "b1", "manual", "a skill",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "failing", "skill", 0.8, 0.8, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    mock_router.chat.side_effect = Exception("LLM API error")

    result = await run_curation(db_path=db_path, router=mock_router)
    assert result["llm_reviewed"] == 0
    assert result["llm_demoted"] == 0
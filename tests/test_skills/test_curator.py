from __future__ import annotations

import time

import aiosqlite
import pytest

from src.skills.curator import run_curation


def _relative_ms(days_ago: int) -> int:
    return int(time.time() - days_ago * 86400) * 1000


@pytest.mark.asyncio
async def test_curation_no_skills(tmp_path):
    db_path = str(tmp_path / "empty.db")

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, description TEXT,
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
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path)
    assert result == {"staled": 0, "archived": 0}


@pytest.mark.asyncio
async def test_curation_skips_pinned(tmp_path):
    db_path = str(tmp_path / "pinned.db")

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, description TEXT,
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
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1", "pinned-skill", "skill", "b1", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 1, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "pinned", "skill", 0.8, 0.8, _relative_ms(100), "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path)
    assert result == {"staled": 0, "archived": 0}


@pytest.mark.asyncio
async def test_curation_stales_old_skill(tmp_path):
    db_path = str(tmp_path / "stale.db")

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, description TEXT,
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
    stale_ts = _relative_ms(31)
    archived_ts = _relative_ms(91)

    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n-stale", "stale-skill", "skill", "b-stale", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b-stale", "stale", "skill", 0.8, 0.8, stale_ts, "skill", 4, "active"),
    )

    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n-arch", "archived-skill", "skill", "b-arch", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b-arch", "archived", "skill", 0.8, 0.8, archived_ts, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path)
    assert result["staled"] >= 1
    assert result["archived"] >= 1


@pytest.mark.asyncio
async def test_curation_recent_skill_not_affected(tmp_path):
    db_path = str(tmp_path / "recent.db")

    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    await conn.execute(
        """
        CREATE TABLE skill_nodes (
            node_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            node_type TEXT, belief_id TEXT, description TEXT,
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
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n-recent", "recent-skill", "skill", "b-recent", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b-recent", "recent", "skill", 0.8, 0.8, _relative_ms(1), "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    result = await run_curation(db_path=db_path)
    assert result == {"staled": 0, "archived": 0}
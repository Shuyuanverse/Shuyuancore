from __future__ import annotations

import time
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from src.skills.manager import PersistentSkillStore


@pytest.fixture
def mock_belief_store():
    store = AsyncMock()
    store.get_by_id = AsyncMock(return_value=None)
    store.update = AsyncMock()
    store.propagate_confidence = AsyncMock()
    return store


@pytest.fixture
async def skill_env(tmp_path, mock_belief_store):
    db_path = str(tmp_path / "propagate.db")
    store = PersistentSkillStore(
        belief_store=mock_belief_store,
        db_path=db_path,
    )
    conn = await store._get_conn()
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_nodes (
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
        CREATE TABLE IF NOT EXISTS beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT DEFAULT '[]',
            emotion REAL DEFAULT 0.5,
            depends_on TEXT DEFAULT '[]',
            child_belief_ids TEXT DEFAULT '[]',
            superseded_by TEXT,
            status TEXT DEFAULT 'active',
            is_composite INTEGER DEFAULT 0,
            timestamp INTEGER DEFAULT 0,
            metadata_json TEXT DEFAULT '{}',
            created_at INTEGER DEFAULT 0,
            updated_at INTEGER DEFAULT 0
        )
        """
    )

    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes (node_id, name, node_type, belief_id, source, description, tags, preconditions, status, is_pinned, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("n1", "test-skill", "skill", "b1", "manual", "a test skill", "[]", "[]", "active", 0, now, now),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "test", "skill", 0.6, 0.6, now, "skill", 4, "active"),
    )
    await conn.commit()
    return store


@pytest.mark.asyncio
async def test_update_skill_propagates_confidence(skill_env, mock_belief_store):
    await skill_env.update_skill({
        "name": "test-skill",
        "confidence": 0.8,
    })

    conn = await skill_env._get_conn()
    cursor = await conn.execute(
        "SELECT confidence, base_confidence FROM beliefs WHERE id = ?",
        ("b1",),
    )
    row = await cursor.fetchone()
    assert row[0] == 0.8
    assert row[1] == 0.8



@pytest.mark.asyncio
async def test_update_skill_no_propagation_without_confidence(skill_env, mock_belief_store):
    await skill_env.update_skill({
        "name": "test-skill",
        "description": "updated description",
    })

    mock_belief_store.propagate_confidence.assert_not_called()


@pytest.mark.asyncio
async def test_update_skill_no_propagation_without_belief_store(tmp_path):
    store = PersistentSkillStore(belief_store=None, db_path=str(tmp_path / "no_belief.db"))
    conn = await store._get_conn()
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_nodes (
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
        CREATE TABLE IF NOT EXISTS beliefs (
            id TEXT PRIMARY KEY, content TEXT, source TEXT,
            confidence REAL, base_confidence REAL,
            last_accessed INTEGER, memory_type TEXT,
            layer INTEGER, entities TEXT DEFAULT '[]',
            emotion REAL DEFAULT 0.5,
            depends_on TEXT DEFAULT '[]',
            child_belief_ids TEXT DEFAULT '[]',
            superseded_by TEXT,
            status TEXT DEFAULT 'active',
            is_composite INTEGER DEFAULT 0,
            timestamp INTEGER DEFAULT 0,
            metadata_json TEXT DEFAULT '{}',
            created_at INTEGER DEFAULT 0,
            updated_at INTEGER DEFAULT 0
        )
        """
    )
    now = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO skill_nodes (node_id, name, node_type, belief_id, source, description, tags, preconditions, status, is_pinned, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("n1", "test-skill", "skill", "b1", "manual", "a test skill", "[]", "[]", "active", 0, now, now),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "test", "skill", 0.6, 0.6, now, "skill", 4, "active"),
    )
    await conn.commit()

    await store.update_skill({
        "name": "test-skill",
        "confidence": 0.9,
    })

    conn2 = await store._get_conn()
    cursor = await conn2.execute(
        "SELECT node_id FROM skill_nodes WHERE name = ?",
        ("test-skill",),
    )
    row = await cursor.fetchone()
    assert row is not None
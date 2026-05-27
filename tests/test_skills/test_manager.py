from __future__ import annotations

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock

from src.skills.manager import PersistentSkillGraph, PersistentSkillStore


async def _setup_db(db_path: str, with_beliefs: bool = True):
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
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
        CREATE TABLE IF NOT EXISTS skill_edges (
            edge_id TEXT PRIMARY KEY, from_node TEXT NOT NULL,
            to_node TEXT NOT NULL, edge_type TEXT, created_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_usage (
            usage_id TEXT PRIMARY KEY, skill_name TEXT NOT NULL,
            conversation_id TEXT, invoked_at INTEGER,
            success INTEGER, user_feedback TEXT, duration_ms INTEGER
        )
        """
    )
    if with_beliefs:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS beliefs (
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


import aiosqlite


@pytest.mark.asyncio
async def test_create_skill():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)

    mock_belief_store = AsyncMock()
    mock_belief_store.add = AsyncMock(return_value="test-belief-id-1")
    store._belief_store = mock_belief_store

    node_id = await store.create_skill(
        {"name": "test-skill", "description": "A test skill"}, "conv-1"
    )
    assert node_id.startswith("sk_")
    os.unlink(path)


@pytest.mark.asyncio
async def test_get_skill():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="test-belief-id-get")

    await store.create_skill({"name": "get-skill", "description": "desc"}, "conv-1")
    retrieved = await store.get_skill("get-skill")
    assert retrieved is not None
    assert retrieved["name"] == "get-skill"
    os.unlink(path)


@pytest.mark.asyncio
async def test_get_skill_not_found():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    retrieved = await store.get_skill("nonexistent")
    assert retrieved is None
    os.unlink(path)


@pytest.mark.asyncio
async def test_list_skills():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="list-belief-id")

    for i in range(3):
        await store.create_skill({"name": f"list-skill-{i}"}, "conv-1")
    skills = await store.list_skills()
    assert len(skills) >= 3
    os.unlink(path)


@pytest.mark.asyncio
async def test_update_skill():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="update-belief-id")

    await store.create_skill({"name": "upd-skill", "description": "old"}, "conv-1")
    await store.update_skill({"name": "upd-skill", "description": "new"})
    retrieved = await store.get_skill("upd-skill")
    assert retrieved["description"] == "new"
    os.unlink(path)


@pytest.mark.asyncio
async def test_delete_skill():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="delete-belief-id")
    store._belief_store.remove = AsyncMock()

    await store.create_skill({"name": "del-skill"}, "conv-1")
    await store.delete_skill("del-skill")
    retrieved = await store.get_skill("del-skill")
    assert retrieved is None
    os.unlink(path)


@pytest.mark.asyncio
async def test_skill_edge():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="edge-belief-id")

    await store.create_skill({"name": "edge-a"}, "conv-1")
    await store.create_skill({"name": "edge-b"}, "conv-1")

    graph = PersistentSkillGraph(db_path=path)
    eid = await graph.add_edge({
        "from_node": "edge-a",
        "to_node": "edge-b",
        "edge_type": "enables",
    })
    assert eid.startswith("se_")

    edges = await graph.get_edges("edge-a")
    assert len(edges) >= 1
    assert edges[0]["to_node"] == "edge-b"
    os.unlink(path)


@pytest.mark.asyncio
async def test_get_skill_by_belief_id():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    store = PersistentSkillStore(db_path=path)
    store._belief_store = AsyncMock()
    store._belief_store.add = AsyncMock(return_value="test-belief-id-lookup")

    await store.create_skill({"name": "lookup-skill"}, "conv-1")
    skill = await store.get_skill_by_belief_id("test-belief-id-lookup")
    assert skill is not None
    assert skill["name"] == "lookup-skill"
    os.unlink(path)


@pytest.mark.asyncio
async def test_skill_usage_logging():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await _setup_db(path)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    now = 1000000
    await conn.execute(
        "INSERT INTO skill_usage (usage_id, skill_name, conversation_id, invoked_at, success) VALUES (?, ?, ?, ?, ?)",
        ("su-test", "test-skill", "conv-1", now, 1),
    )
    await conn.commit()
    cursor = await conn.execute("SELECT * FROM skill_usage WHERE usage_id = ?", ("su-test",))
    row = await cursor.fetchone()
    assert row is not None
    assert row["success"] == 1
    await conn.close()
    os.unlink(path)
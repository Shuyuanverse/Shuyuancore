from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest


@pytest.fixture(autouse=True)
def _patch_model_provider():
    with patch("src.evolution.module_manager.get_model_provider"):
        yield


class MockBelief:
    def __init__(self, id="test-belief"):
        self.id = id
        self.content = "test"
        self.source = "user"
        self.confidence = 0.8
        self.last_accessed = 1000
        self.memory_type = "chat"
        self.layer = 3
        self.status = "active"

    def __repr__(self):
        return f"MockBelief(id={self.id})"


@pytest.mark.asyncio
async def test_agent_initialized_with_skill_store():
    from src.core.agent import Agent

    agent = Agent(
        model_provider=AsyncMock(),
        belief_store=AsyncMock(),
        reader=AsyncMock(),
        skill_store=MagicMock(),
    )
    assert agent._skill_store is not None


@pytest.mark.asyncio
async def test_agent_initialized_without_skill_store():
    from src.core.agent import Agent

    agent = Agent(
        model_provider=AsyncMock(),
        belief_store=AsyncMock(),
        reader=AsyncMock(),
    )
    assert agent._skill_store is None


@pytest.mark.asyncio
async def test_chat_stream_with_mocked_skill_store():
    from src.core.agent import Agent

    mock_provider = AsyncMock()
    mock_evt = MagicMock()
    mock_evt.type = "content"
    mock_evt.content = "response"

    async def mock_stream(*args, **kwargs):
        yield mock_evt

    mock_provider.chat_stream = mock_stream

    mock_reader = AsyncMock()
    mock_reader.read = AsyncMock(
        return_value=[{"role": "user", "content": "hello"}]
    )

    mock_belief_store = AsyncMock()
    mock_belief_store.add = AsyncMock(return_value="b-1")
    mock_belief_store.search_similar = AsyncMock(return_value=[])
    mock_belief_store.get = AsyncMock(return_value=[])
    mock_belief_store.update = AsyncMock()

    mock_skill_store = AsyncMock()
    mock_skill_store.list_skills = AsyncMock(return_value=[])
    mock_skill_store.get_skill_by_belief_id = AsyncMock(return_value=None)

    agent = Agent(
        model_provider=mock_provider,
        belief_store=mock_belief_store,
        reader=mock_reader,
        skill_store=mock_skill_store,
    )

    chunks = []
    async for chunk in agent.chat_stream("hello", "conv-1"):
        chunks.append(chunk)
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_background_update_with_skill_store():
    from src.core.agent import Agent

    mock_provider = AsyncMock()
    mock_reader = AsyncMock()
    mock_reader.read = AsyncMock(return_value=[])

    mock_belief_store = AsyncMock()
    mock_belief_store.get = AsyncMock(return_value=[MockBelief()])
    mock_belief_store.search_similar = AsyncMock(return_value=[])
    mock_belief_store.add = AsyncMock(return_value="b-1")
    mock_belief_store.update = AsyncMock()

    mock_skill_store = AsyncMock()

    agent = Agent(
        model_provider=mock_provider,
        belief_store=mock_belief_store,
        reader=mock_reader,
        skill_store=mock_skill_store,
    )

    await agent._background_update(
        message="test",
        response="test response",
        conversation_id="conv-1",
    )
    assert mock_belief_store.update.called


@pytest.mark.asyncio
async def test_chat_stream_skill_context_injection():
    from src.core.agent import Agent

    mock_provider = AsyncMock()
    mock_evt = MagicMock()
    mock_evt.type = "content"
    mock_evt.content = "skilled response"

    async def mock_stream(*args, **kwargs):
        yield mock_evt

    mock_provider.chat_stream = mock_stream

    mock_reader = AsyncMock()
    mock_reader.read = AsyncMock(
        return_value=[{"role": "user", "content": "how to test api"}]
    )

    mock_belief_store = AsyncMock()
    mock_belief_store.add = AsyncMock(return_value="b-1")
    mock_belief_store.search_similar = AsyncMock(return_value=[])
    mock_belief_store.get = AsyncMock(return_value=[])
    mock_belief_store.update = AsyncMock()

    mock_skill_store = MagicMock()
    mock_skill_store.list_skills = AsyncMock(return_value=[])
    mock_skill_store.get_skill_by_belief_id = AsyncMock(return_value=None)

    agent = Agent(
        model_provider=mock_provider,
        belief_store=mock_belief_store,
        reader=mock_reader,
        skill_store=mock_skill_store,
    )

    chunks = []
    async for chunk in agent.chat_stream("how to test api", "conv-2"):
        chunks.append(chunk)
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_skill_graph_edge_sync_to_belief():
    from src.skills.manager import PersistentSkillGraph, PersistentSkillStore

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = await aiosqlite.connect(path)
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
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_edges (
            edge_id TEXT PRIMARY KEY, from_node TEXT NOT NULL,
            to_node TEXT NOT NULL, edge_type TEXT, created_at INTEGER
        )
        """
    )
    now = 1000000
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status, depends_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("ba", "skill a", "skill", 0.8, 0.8, now, "skill", 4, "active", "[]"),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status, depends_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("bb", "skill b", "skill", 0.7, 0.7, now, "skill", 4, "active", "[]"),
    )
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n-from", "skill-a", "skill", "ba", "manual", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n-to", "skill-b", "skill", "bb", "manual", "desc",
            "[]", "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.commit()

    graph = PersistentSkillGraph(db_path=path)
    await graph.add_edge({
        "from_node": "skill-a",
        "to_node": "skill-b",
        "edge_type": "enables",
    })

    cursor = await conn.execute(
        "SELECT depends_on FROM beliefs WHERE id = ?", ("ba",)
    )
    row = await cursor.fetchone()
    deps_raw = row[0] if row else "[]"
    deps = json.loads(deps_raw) if deps_raw else []

    assert "bb" in deps
    await conn.close()
    os.unlink(path)
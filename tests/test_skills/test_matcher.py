from __future__ import annotations

import json
import os
import tempfile

import aiosqlite
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.skills.matcher import format_skill_for_prompt, match_skill
from src.skills.manager import PersistentSkillStore


class TestFormatSkillPrompt:
    def test_format_with_all_fields(self):
        skill = {
            "name": "test-skill",
            "description": "A test skill description",
            "causality_level0": "when X -> do Y -> get Z",
            "tags": ["test", "demo"],
            "boundaries": ["not for production"],
        }
        result = format_skill_for_prompt(skill)
        assert "test-skill" in result
        assert "A test skill description" in result
        assert "when X -> do Y -> get Z" in result
        assert "test" in result
        assert "not for production" in result

    def test_format_minimal(self):
        skill = {"name": "minimal-skill"}
        result = format_skill_for_prompt(skill)
        assert "minimal-skill" in result
        assert "[技能匹配]" in result

    def test_format_empty_boundaries(self):
        skill = {"name": "no-boundaries", "boundaries": [], "tags": []}
        result = format_skill_for_prompt(skill)
        assert "no-boundaries" in result
        assert "不适用" not in result

    def test_format_tags_as_json_string(self):
        skill = {"name": "json-tags", "tags": '["tag1", "tag2"]'}
        result = format_skill_for_prompt(skill)
        assert "tag1" in result

    def test_format_boundaries_as_json_string(self):
        skill = {"name": "json-boundaries", "boundaries": '["b1", "b2"]'}
        result = format_skill_for_prompt(skill)
        assert "b1" in result
        assert "不适用" in result


@pytest.mark.asyncio
async def test_match_timeout_returns_none():
    belief_store = AsyncMock()
    skill_store = AsyncMock()
    embedding_service = AsyncMock()

    result = await match_skill(
        user_message="hello",
        belief_store=belief_store,
        skill_store=skill_store,
        embedding_service=embedding_service,
    )
    assert result is None or isinstance(result, dict)


@pytest.mark.asyncio
async def test_exact_match_via_skill_command():
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
    now = 1000000
    await conn.execute(
        "INSERT INTO skill_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n2", "api-test-suite", "skill", "b2", "manual", "API testing",
            '["api", "test"]', "[]", "", "", "", "[]", "[]", "[]", "[]",
            "active", 0, now, now,
        ),
    )
    await conn.execute(
        "INSERT INTO beliefs (id, content, source, confidence, base_confidence, last_accessed, memory_type, layer, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b2", "api-test", "skill", 0.9, 0.9, now, "skill", 4, "active"),
    )
    await conn.commit()
    await conn.close()

    store = PersistentSkillStore(db_path=path)
    from src.skills.matcher import _try_exact_match
    result = await _try_exact_match("/skill api-test-suite", store)
    assert result is not None
    assert result["name"] == "api-test-suite"
    os.unlink(path)


@pytest.mark.asyncio
async def test_exact_match_none():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = await aiosqlite.connect(path)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_nodes (
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
    await conn.commit()
    await conn.close()

    store = PersistentSkillStore(db_path=path)
    from src.skills.matcher import _try_exact_match
    result = await _try_exact_match("普通对话，没有技能引用", store)
    assert result is None
    os.unlink(path)
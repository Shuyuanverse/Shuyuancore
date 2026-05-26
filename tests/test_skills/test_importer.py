from __future__ import annotations

import json
import os
import zipfile

import pytest
from unittest.mock import AsyncMock, patch

from src.exceptions import SkillImportError
from src.skills.importer import export_skills, import_skills
from src.skills.manager import PersistentSkillGraph, PersistentSkillStore


@pytest.fixture
async def skill_env(tmp_path):
    db_path = str(tmp_path / "import_test.db")
    store = PersistentSkillStore(db_path=db_path)
    conn = await store._get_conn()
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

    graph = PersistentSkillGraph(db_path=db_path)
    return store, graph


@pytest.mark.asyncio
async def test_export_nonexistent_skill(skill_env):
    store, graph = skill_env
    with pytest.raises(Exception):
        await export_skills(["nonexistent-skill"], store, graph)


@pytest.mark.asyncio
async def test_export_and_import_roundtrip(skill_env, tmp_path):
    store, graph = skill_env

    await store.create_skill(
        {
            "name": "roundtrip-skill",
            "description": "Roundtrip test skill",
            "tags": ["test"],
            "causality_level0": "when A -> do B -> get C",
        },
        "conv-1",
    )

    zip_path = await export_skills(
        ["roundtrip-skill"], store, graph,
        output_path=str(tmp_path / "export.zip"),
    )
    assert os.path.exists(zip_path)

    await store.delete_skill("roundtrip-skill")

    result = await import_skills(zip_path, store, graph)
    assert "roundtrip-skill" in result["imported"]

    imported = await store.get_skill("roundtrip-skill")
    assert imported is not None
    assert imported["description"] == "Roundtrip test skill"


@pytest.mark.asyncio
async def test_import_missing_manifest(skill_env, tmp_path):
    store, graph = skill_env
    bad_zip = tmp_path / "no_manifest.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("random.txt", "data")

    with pytest.raises(SkillImportError, match="manifest.json"):
        await import_skills(str(bad_zip), store, graph)


@pytest.mark.asyncio
async def test_import_unsupported_schema(skill_env, tmp_path):
    store, graph = skill_env
    bad_zip = tmp_path / "bad_schema.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"schema_version": "0.5", "skills": []}),
        )

    with pytest.raises(SkillImportError, match="schema"):
        await import_skills(str(bad_zip), store, graph)


@pytest.mark.asyncio
async def test_import_missing_dependencies(skill_env, tmp_path):
    store, graph = skill_env

    zip_path = tmp_path / "dep_missing.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({
                "schema_version": "1.0",
                "skills": ["dependent-skill"],
                "dependencies": ["missing-dep"],
            }),
        )
        import os
        zf.writestr(
            "skills/dependent-skill_node.json",
            json.dumps({
                "name": "dependent-skill",
                "description": "Has missing dep",
            }),
        )

    result = await import_skills(str(zip_path), store, graph)
    assert "missing-dep" in result["missing_dependencies"]
    assert "dependent-skill" in result["incomplete"] or "dependent-skill" in result["imported"]


@pytest.mark.asyncio
async def test_import_duplicate_local_skill_skipped(skill_env, tmp_path):
    store, graph = skill_env

    await store.create_skill(
        {
            "name": "local-skill",
            "description": "Already exists locally",
            "version_history": [{"version": "1.0"}],
        },
        "conv-1",
    )

    zip_path = tmp_path / "dup_local.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({
                "schema_version": "1.0",
                "skills": ["local-skill"],
                "dependencies": [],
            }),
        )
        zf.writestr(
            "skills/local-skill_node.json",
            json.dumps({
                "name": "local-skill",
                "description": "Trying to override",
            }),
        )

    result = await import_skills(str(zip_path), store, graph)
    assert "local-skill" in result["skipped"]

    skill = await store.get_skill("local-skill")
    assert skill is not None
    assert skill["description"] == "Already exists locally"
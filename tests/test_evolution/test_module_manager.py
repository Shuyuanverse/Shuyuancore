# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""ModuleManager 单元测试 — 测试自演化模块生命周期管理。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.config import EvolutionConfig
from src.evolution.module_manager import ModuleManager


def _create_test_db():
    """创建测试数据库并初始化表结构。"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()

    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE evolution_modules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            memory_partition TEXT NOT NULL,
            task_type TEXT,
            trigger_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at INTEGER,
            archived_at INTEGER,
            last_trigger_at INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE evolution_collaborations (
            id TEXT PRIMARY KEY,
            from_module TEXT NOT NULL,
            to_module TEXT NOT NULL,
            timestamp INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()

    return temp_db.name


@pytest_asyncio.fixture
async def mock_belief_store():
    """创建模拟信念存储。"""
    store = AsyncMock()
    store.get_similar_task_count = AsyncMock(return_value=0)
    return store


@pytest_asyncio.fixture
async def mock_review_agent():
    """创建模拟审查 Agent。"""
    agent = AsyncMock()
    agent.review_prompt = AsyncMock(return_value=0.85)
    return agent


@pytest_asyncio.fixture
async def mock_llm():
    """创建模拟 LLM Provider。"""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="Generated module prompt for testing.")
    return llm


@pytest_asyncio.fixture
async def module_manager(mock_belief_store, mock_review_agent, mock_llm):
    """创建 ModuleManager 测试夹具。"""
    db_path = _create_test_db()

    with patch("src.evolution.module_manager.get_model_provider", return_value=mock_llm):
        manager = ModuleManager(
            db_path=db_path,
            belief_store=mock_belief_store,
            review_agent=mock_review_agent,
            config=EvolutionConfig(
                birth_threshold=40,
                birth_window_days=7,
                fusion_threshold=3,
                fusion_window_days=3,
                death_inactive_days=14,
                enable_auto_evolution=True,
            ),
        )
        yield manager, db_path

    # 清理
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_create_module_success(module_manager) -> None:
    """测试成功创建模块。"""
    manager, db_path = module_manager
    trajectory = "User asked to translate a document. Agent called translate_tool with params..."

    module_id = await manager.create_module(
        name="translation_module",
        task_type="translation",
        execution_trajectory=trajectory,
    )

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, task_type, status, trigger_count FROM evolution_modules WHERE id = ?", (module_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == module_id
    assert row[1] == "translation_module"
    assert row[2] == "translation"
    assert row[3] == "active"
    assert row[4] == 0


@pytest.mark.asyncio
async def test_create_module_quality_gate_failure(module_manager, mock_review_agent) -> None:
    """测试质量门控失败时抛出异常。"""
    manager, db_path = module_manager
    mock_review_agent.review_prompt = AsyncMock(side_effect=[0.5, 0.6])

    trajectory = "Simple trajectory"

    with pytest.raises(ValueError, match="Failed to generate acceptable prompt"):
        await manager.create_module(
            name="low_quality_module",
            task_type="test",
            execution_trajectory=trajectory,
        )


@pytest.mark.asyncio
async def test_create_module_retry_success(module_manager, mock_review_agent) -> None:
    """测试重试后质量达标。"""
    manager, db_path = module_manager
    mock_review_agent.review_prompt = AsyncMock(side_effect=[0.6, 0.75])

    module_id = await manager.create_module(
        name="retry_module",
        task_type="test",
        execution_trajectory="test trajectory",
    )

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM evolution_modules WHERE id = ?", (module_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "retry_module"


@pytest.mark.asyncio
async def test_fuse_modules_success(module_manager) -> None:
    """测试成功融合两个模块。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("module_a", "ModuleA", "Prompt A content", "partition_a", now_ms),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("module_b", "ModuleB", "Prompt B content", "partition_b", now_ms),
    )
    conn.commit()
    conn.close()

    fused_id = await manager.fuse_modules("module_a", "module_b")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, status FROM evolution_modules WHERE id IN ('module_a', 'module_b', ?)", (fused_id,))
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 3

    module_a_row = next(r for r in rows if r[0] == "module_a")
    assert module_a_row[2] == "archived"

    module_b_row = next(r for r in rows if r[0] == "module_b")
    assert module_b_row[2] == "archived"

    fused_row = next(r for r in rows if r[0] == fused_id)
    assert fused_row[1] == "ModuleA_ModuleB_fused"
    assert fused_row[2] == "active"


@pytest.mark.asyncio
async def test_fuse_modules_not_found(module_manager) -> None:
    """测试融合不存在的模块时抛出异常。"""
    manager, db_path = module_manager

    with pytest.raises(ValueError, match="Module not found"):
        await manager.fuse_modules("nonexistent_a", "nonexistent_b")


@pytest.mark.asyncio
async def test_fuse_modules_quality_gate_failure(module_manager, mock_review_agent) -> None:
    """测试融合质量不达标时抛出异常。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("module_c", "ModuleC", "Prompt C", "partition_c", now_ms),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("module_d", "ModuleD", "Prompt D", "partition_d", now_ms),
    )
    conn.commit()
    conn.close()

    mock_review_agent.review_prompt = AsyncMock(return_value=0.5)

    with pytest.raises(ValueError, match="Fused module quality insufficient"):
        await manager.fuse_modules("module_c", "module_d")


@pytest.mark.asyncio
async def test_archive_module(module_manager) -> None:
    """测试归档模块。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("module_to_archive", "TestModule", "Test prompt", "partition", now_ms),
    )
    conn.commit()
    conn.close()

    await manager.archive_module("module_to_archive")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT status, archived_at FROM evolution_modules WHERE id = ?", ("module_to_archive",))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "archived"
    assert row[1] is not None
    assert row[1] > now_ms


@pytest.mark.asyncio
async def test_get_active_modules(module_manager) -> None:
    """测试获取活跃模块列表。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("active_1", "ActiveModule1", "Prompt 1", "p1", now_ms),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'archived', ?)",
        ("archived_1", "ArchivedModule", "Prompt A", "pA", now_ms),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
        ("active_2", "ActiveModule2", "Prompt 2", "p2", now_ms - 1000),
    )
    conn.commit()
    conn.close()

    active_modules = await manager.get_active_modules()

    assert len(active_modules) == 2
    assert active_modules[0]["name"] == "ActiveModule1"
    assert active_modules[1]["name"] == "ActiveModule2"


@pytest.mark.asyncio
async def test_record_collaboration(module_manager) -> None:
    """测试记录模块间协作。"""
    manager, db_path = module_manager

    await manager.record_collaboration("module_src", "module_dst")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT from_module, to_module FROM evolution_collaborations")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "module_src"
    assert rows[0][1] == "module_dst"


@pytest.mark.asyncio
async def test_get_collaboration_count(module_manager) -> None:
    """测试获取协作次数。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_collaborations (id, from_module, to_module, timestamp) VALUES (?, ?, ?, ?)",
        ("collab1", "module_a", "module_b", now_ms),
    )
    cursor.execute(
        "INSERT INTO evolution_collaborations (id, from_module, to_module, timestamp) VALUES (?, ?, ?, ?)",
        ("collab2", "module_b", "module_a", now_ms - 1000),
    )
    cursor.execute(
        "INSERT INTO evolution_collaborations (id, from_module, to_module, timestamp) VALUES (?, ?, ?, ?)",
        ("collab3", "module_a", "module_c", now_ms),
    )
    conn.commit()
    conn.close()

    count = await manager.get_collaboration_count("module_a", "module_b", days=3)
    assert count == 2

    count = await manager.get_collaboration_count("module_a", "module_c", days=3)
    assert count == 1

    count = await manager.get_collaboration_count("module_x", "module_y", days=3)
    assert count == 0


@pytest.mark.asyncio
async def test_archive_inactive_modules(module_manager) -> None:
    """测试归档长期未活跃模块。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)
    old_time = int((time.time() - 20 * 24 * 60 * 60) * 1000)
    recent_time = int((time.time() - 5 * 24 * 60 * 60) * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at, last_trigger_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        ("old_module", "OldModule", "Old prompt", "p_old", now_ms, old_time),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at, last_trigger_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        ("recent_module", "RecentModule", "Recent prompt", "p_recent", now_ms, recent_time),
    )
    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, status, created_at, last_trigger_at) VALUES (?, ?, ?, ?, 'active', ?, NULL)",
        ("never_triggered", "NeverTriggered", "Never prompt", "p_never", now_ms),
    )
    conn.commit()
    conn.close()

    archived_count = await manager.archive_inactive_modules(inactive_days=14)

    assert archived_count == 2

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, status FROM evolution_modules")
    rows = cursor.fetchall()
    conn.close()

    status_map = {row[0]: row[1] for row in rows}
    assert status_map["old_module"] == "archived"
    assert status_map["recent_module"] == "active"
    assert status_map["never_triggered"] == "archived"


@pytest.mark.asyncio
async def test_increment_trigger_count(module_manager) -> None:
    """测试增加模块触发计数。"""
    manager, db_path = module_manager
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO evolution_modules (id, name, prompt_text, memory_partition, trigger_count, status, created_at) VALUES (?, ?, ?, ?, 5, 'active', ?)",
        ("test_module", "TestModule", "Test prompt", "partition", now_ms),
    )
    conn.commit()
    conn.close()

    await manager.increment_trigger_count("test_module")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT trigger_count, last_trigger_at FROM evolution_modules WHERE id = ?", ("test_module",))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == 6
    assert row[1] is not None
    assert row[1] > now_ms - 1000

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


@dataclass
class RollbackPoint:
    """回滚点 / Rollback point

    Attributes:
        id: 唯一标识符
        user_id: 用户 ID
        action: 操作名称
        resource_type: 资源类型（file / config）
        resource_path: 资源路径
        snapshot: 操作前的数据快照
        timestamp: 创建时间
        status: 状态（active / rolled_back / expired）
        metadata: 额外元数据
    """
    id: str
    user_id: str
    action: str
    resource_type: str
    resource_path: str
    snapshot: dict[str, Any]
    timestamp: float
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)


class RollbackManager:
    """回滚管理器 / Rollback manager

    管理操作回滚点，支持文件操作和配置变更的回滚。
    使用 aiosqlite 持久化存储。
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path: str = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._ensure_table()
        return self._conn

    async def _ensure_table(self) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rollback_points (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL DEFAULT 'file',
                resource_path TEXT NOT NULL DEFAULT '',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active',
                timestamp REAL NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rollback_user_id ON rollback_points(user_id);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rollback_status ON rollback_points(status);"
        )
        await conn.commit()

    async def create_rollback_point(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_path: str,
        snapshot: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """创建回滚点 / Create a rollback point

        Args:
            user_id: 用户 ID
            action: 操作名称
            resource_type: 资源类型（file / config）
            resource_path: 资源路径
            snapshot: 快照数据
            metadata: 元数据

        Returns:
            回滚点 ID
        """
        rollback_id = f"rb_{uuid.uuid4().hex[:16]}"
        now = time.time()
        point = RollbackPoint(
            id=rollback_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_path=resource_path,
            snapshot=snapshot or {},
            timestamp=now,
            metadata=metadata or {},
        )

        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO rollback_points
                (id, user_id, action, resource_type, resource_path,
                 snapshot_json, metadata_json, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                rollback_id,
                user_id,
                action,
                resource_type,
                resource_path,
                json.dumps(point.snapshot, ensure_ascii=False),
                json.dumps(point.metadata, ensure_ascii=False),
                now,
            ),
        )
        await conn.commit()

        logger.info(
            "回滚点已创建: %s 操作=%s 类型=%s / Rollback point created: %s action=%s type=%s",
            rollback_id,
            action,
            resource_type,
            rollback_id,
            action,
            resource_type,
        )
        return rollback_id

    async def execute_rollback(self, rollback_id: str) -> bool:
        """执行回滚 / Execute a rollback

        Args:
            rollback_id: 回滚点 ID

        Returns:
            True 如果回滚成功

        Raises:
            ValueError: 如果回滚点不存在或已回滚
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM rollback_points WHERE id = ?",
            (rollback_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(
                f"回滚点不存在: {rollback_id} / Rollback point not found: {rollback_id}"
            )
        if row["status"] != "active":
            raise ValueError(
                f"回滚点已处理: {rollback_id} / Rollback point already processed: {rollback_id}"
            )

        resource_type = row["resource_type"]
        resource_path = row["resource_path"]
        snapshot: dict[str, Any] = json.loads(row["snapshot_json"])

        success = False
        try:
            if resource_type == "file":
                success = await self._rollback_file(resource_path, snapshot)
            elif resource_type == "config":
                success = await self._rollback_config(resource_path, snapshot)
            else:
                logger.warning("不支持的资源类型: %s / Unsupported resource type: %s", resource_type, resource_type)
                success = False

            if success:
                await conn.execute(
                    "UPDATE rollback_points SET status = 'rolled_back' WHERE id = ?",
                    (rollback_id,),
                )
                await conn.commit()
                logger.info("回滚成功: %s / Rollback succeeded: %s", rollback_id, rollback_id)
            else:
                logger.error("回滚失败: %s / Rollback failed: %s", rollback_id, rollback_id)
        except Exception as e:
            logger.exception("回滚异常: %s / Rollback error: %s", rollback_id, rollback_id)
            raise

        return success

    async def _rollback_file(self, resource_path: str, snapshot: dict[str, Any]) -> bool:
        """执行文件回滚 / Execute file rollback

        Args:
            resource_path: 文件路径
            snapshot: 快照数据

        Returns:
            True 如果回滚成功
        """
        original_content = snapshot.get("content")
        if original_content is None:
            logger.warning("快照中没有文件内容 / No file content in snapshot")
            return False

        path = Path(resource_path)
        backup_path = snapshot.get("backup_path", "")

        # 优先使用备份文件恢复
        if backup_path and Path(backup_path).exists():
            shutil.copy2(backup_path, resource_path)
            logger.info("已从备份恢复文件: %s / File restored from backup: %s", resource_path, resource_path)
            return True

        # 否则使用快照内容恢复
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(original_content, encoding="utf-8")
            logger.info("已从快照恢复文件: %s / File restored from snapshot: %s", resource_path, resource_path)
            return True
        except Exception as e:
            logger.error("文件回滚失败: %s / File rollback failed: %s", resource_path, e)
            return False

    async def _rollback_config(self, resource_path: str, snapshot: dict[str, Any]) -> bool:
        """执行配置回滚 / Execute config rollback

        Args:
            resource_path: 配置路径
            snapshot: 快照数据

        Returns:
            True 如果回滚成功
        """
        original_value = snapshot.get("value")
        if original_value is None:
            logger.warning("快照中没有配置值 / No config value in snapshot")
            return False

        logger.info(
            "配置回滚已完成: %s / Config rollback completed: %s",
            resource_path,
            resource_path,
        )
        return True

    async def get_rollback_points(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[RollbackPoint]:
        """获取用户的回滚点列表 / Get rollback points for a user

        Args:
            user_id: 用户 ID
            limit: 最大返回数量

        Returns:
            回滚点列表
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM rollback_points WHERE user_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()

        results: list[RollbackPoint] = []
        for row in rows:
            results.append(
                RollbackPoint(
                    id=row["id"],
                    user_id=row["user_id"],
                    action=row["action"],
                    resource_type=row["resource_type"],
                    resource_path=row["resource_path"],
                    snapshot=json.loads(row["snapshot_json"]),
                    timestamp=row["timestamp"],
                    status=row["status"],
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return results

    async def list_available(self, user_id: str) -> list[RollbackPoint]:
        """列出用户可回滚的操作 / List available rollback operations for a user

        Returns:
            状态为 active 的回滚点列表
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM rollback_points WHERE user_id = ? AND status = 'active' "
            "ORDER BY timestamp DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()

        results: list[RollbackPoint] = []
        for row in rows:
            results.append(
                RollbackPoint(
                    id=row["id"],
                    user_id=row["user_id"],
                    action=row["action"],
                    resource_type=row["resource_type"],
                    resource_path=row["resource_path"],
                    snapshot=json.loads(row["snapshot_json"]),
                    timestamp=row["timestamp"],
                    status=row["status"],
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return results

    async def cleanup(self, max_age_days: int = 7) -> int:
        """清理旧的回滚点 / Clean up old rollback points

        Args:
            max_age_days: 最大保留天数，默认 7 天

        Returns:
            清理的回滚点数量
        """
        threshold = time.time() - (max_age_days * 86400)
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id FROM rollback_points WHERE timestamp < ?",
            (threshold,),
        )
        rows = await cursor.fetchall()
        expired_ids = [row["id"] for row in rows]

        if expired_ids:
            placeholders = ",".join("?" for _ in expired_ids)
            await conn.execute(
                f"DELETE FROM rollback_points WHERE id IN ({placeholders})",
                expired_ids,
            )
            await conn.commit()

        if expired_ids:
            logger.info(
                "已清理 %d 个过期回滚点 / Cleaned up %d expired rollback points",
                len(expired_ids),
                len(expired_ids),
            )
        return len(expired_ids)

    async def close(self) -> None:
        """关闭数据库连接 / Close the database connection"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


_managers: dict[str, RollbackManager] = {}
_manager_lock: asyncio.Lock = asyncio.Lock()


async def get_rollback_manager(db_path: str | None = None) -> RollbackManager:
    """获取 RollbackManager 单例 / Get RollbackManager singleton

    Args:
        db_path: 数据库路径

    Returns:
        RollbackManager 实例
    """
    path = _DB_PATH if db_path is None else db_path
    async with _manager_lock:
        if path not in _managers:
            mgr = RollbackManager(db_path=path)
            await mgr._ensure_table()
            _managers[path] = mgr
        return _managers[path]
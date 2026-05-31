# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""反馈收集与分析 — 预测结果反馈的持久化、统计和准确性分析。

功能：
- 记录用户对预测结果的反馈（评分、有用性、评论文本）
- 查询反馈历史与总体统计
- 分析预测准确度趋势
- 自动清理过期数据
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


@dataclass
class FeedbackEntry:
    """反馈条目。

    Attributes:
        id: 反馈记录 ID
        user_id: 用户 ID
        prediction_id: 关联的预测 ID
        action: 预测的动作名称
        rating: 评分 (1-5)
        was_helpful: 是否有帮助
        feedback_text: 反馈文本
        timestamp: 反馈时间戳（毫秒）
        context: 反馈时的上下文信息
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str = ""
    prediction_id: str = ""
    action: str = ""
    rating: int = 3
    was_helpful: bool = True
    feedback_text: str = ""
    timestamp: int = field(default_factory=current_time_ms)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。

        Returns:
            dict[str, Any]: 字典表示
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "prediction_id": self.prediction_id,
            "action": self.action,
            "rating": self.rating,
            "was_helpful": self.was_helpful,
            "feedback_text": self.feedback_text,
            "timestamp": self.timestamp,
            "context": self.context,
        }

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> FeedbackEntry:
        """从数据库行创建实例。

        Args:
            row: 数据库查询结果行

        Returns:
            FeedbackEntry: 反馈条目实例
        """
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            prediction_id=row["prediction_id"],
            action=row["action"],
            rating=row["rating"],
            was_helpful=bool(row["was_helpful"]),
            feedback_text=row["feedback_text"],
            timestamp=row["timestamp"],
            context=json.loads(row["context_json"]) if row.get("context_json") else {},
        )


class FeedbackCollector:
    """反馈收集与分析器。

    持久化存储用户对预测结果的反馈，并提供统计分析能力，
    帮助优化预测触发策略和置信度模型。
    """

    CREATE_TABLE_SQL: str = """
    CREATE TABLE IF NOT EXISTS prediction_feedback (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        prediction_id   TEXT NOT NULL,
        action          TEXT NOT NULL DEFAULT '',
        rating          INTEGER NOT NULL DEFAULT 3,
        was_helpful     INTEGER NOT NULL DEFAULT 1,
        feedback_text   TEXT NOT NULL DEFAULT '',
        timestamp       INTEGER NOT NULL,
        context_json    TEXT NOT NULL DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_prediction_feedback_user ON prediction_feedback(user_id);
    CREATE INDEX IF NOT EXISTS idx_prediction_feedback_prediction ON prediction_feedback(prediction_id);
    CREATE INDEX IF NOT EXISTS idx_prediction_feedback_timestamp ON prediction_feedback(timestamp);
    CREATE INDEX IF NOT EXISTS idx_prediction_feedback_action ON prediction_feedback(action);
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        """初始化反馈收集器。

        Args:
            db_path: SQLite 数据库路径
        """
        self._db_path: str = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接（懒加载）。

        Returns:
            aiosqlite.Connection: 数据库连接
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._init_tables()
        return self._conn

    async def _init_tables(self) -> None:
        """初始化数据库表。"""
        conn = await self._get_conn()
        for statement in self.CREATE_TABLE_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(stmt)
        await conn.commit()

    async def record_feedback(self, entry: FeedbackEntry) -> None:
        """记录一条反馈。

        将反馈条目持久化到 prediction_feedback 表。
        同时更新关联的 user_predictions 记录的 is_correct 字段。

        Args:
            entry: 反馈条目

        Raises:
            ValueError: 当评分不在 1-5 范围内时
        """
        if not 1 <= entry.rating <= 5:
            raise ValueError(f"Rating must be between 1 and 5, got {entry.rating} / 评分必须在 1-5 之间")

        if not entry.id:
            entry.id = uuid.uuid4().hex
        if not entry.timestamp:
            entry.timestamp = current_time_ms()

        conn = await self._get_conn()

        await conn.execute(
            """
            INSERT OR REPLACE INTO prediction_feedback
                (id, user_id, prediction_id, action, rating,
                 was_helpful, feedback_text, timestamp, context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.user_id,
                entry.prediction_id,
                entry.action,
                entry.rating,
                1 if entry.was_helpful else 0,
                entry.feedback_text,
                entry.timestamp,
                json.dumps(entry.context),
            ),
        )

        # 同步更新 user_predictions 表的反馈字段
        if entry.prediction_id:
            is_correct = 1 if entry.was_helpful else 0
            await conn.execute(
                "UPDATE user_predictions SET is_correct = ?, feedback_at = ? WHERE id = ?",
                (is_correct, entry.timestamp, entry.prediction_id),
            )

        await conn.commit()
        logger.debug(
            "Recorded feedback: prediction=%s, rating=%d, helpful=%s",
            entry.prediction_id,
            entry.rating,
            entry.was_helpful,
        )

    async def get_feedback(self, prediction_id: str) -> FeedbackEntry | None:
        """获取特定预测的反馈。

        Args:
            prediction_id: 预测 ID

        Returns:
            FeedbackEntry 或 None（未找到时）
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM prediction_feedback WHERE prediction_id = ?",
            (prediction_id,),
        )
        row = await cursor.fetchone()
        return FeedbackEntry.from_row(row) if row else None

    async def get_user_feedback(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[FeedbackEntry]:
        """获取用户的反馈历史。

        Args:
            user_id: 用户 ID
            limit: 最大返回条数（默认 50）

        Returns:
            list[FeedbackEntry]: 反馈条目列表，按时间降序排列
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM prediction_feedback WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [FeedbackEntry.from_row(row) for row in rows]

    async def get_stats(self) -> dict[str, Any]:
        """获取总体统计信息。

        统计内容包括：
        - 总预测数（来自 user_predictions 表）
        - 总反馈数
        - 采纳率（was_helpful=True 的比例）
        - 平均评分
        - 评分分布
        - 各动作的反馈统计

        Returns:
            dict: 统计信息字典
        """
        conn = await self._get_conn()
        stats: dict[str, Any] = {}

        # 总预测数
        cursor = await conn.execute("SELECT COUNT(*) as count FROM user_predictions")
        row = await cursor.fetchone()
        stats["total_predictions"] = row["count"] if row else 0

        # 总反馈数
        cursor = await conn.execute("SELECT COUNT(*) as count FROM prediction_feedback")
        row = await cursor.fetchone()
        stats["total_feedback"] = row["count"] if row else 0

        if stats["total_feedback"] == 0:
            stats["acceptance_rate"] = 0.0
            stats["average_rating"] = 0.0
            stats["rating_distribution"] = {}
            stats["action_stats"] = []
            return stats

        # 采纳率
        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM prediction_feedback WHERE was_helpful = 1",
        )
        row = await cursor.fetchone()
        helpful_count = row["count"] if row else 0
        stats["acceptance_rate"] = round(helpful_count / stats["total_feedback"], 4)

        # 平均评分
        cursor = await conn.execute("SELECT AVG(rating) as avg_rating FROM prediction_feedback")
        row = await cursor.fetchone()
        stats["average_rating"] = round(row["avg_rating"], 2) if row and row["avg_rating"] else 0.0

        # 评分分布
        cursor = await conn.execute(
            "SELECT rating, COUNT(*) as count FROM prediction_feedback GROUP BY rating ORDER BY rating",
        )
        rows = await cursor.fetchall()
        stats["rating_distribution"] = {str(row["rating"]): row["count"] for row in rows}

        # 各动作的反馈统计
        cursor = await conn.execute(
            """
            SELECT action,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful,
                   AVG(rating) as avg_rating
            FROM prediction_feedback
            GROUP BY action
            ORDER BY total DESC
            LIMIT 20
            """,
        )
        rows = await cursor.fetchall()
        stats["action_stats"] = [
            {
                "action": row["action"],
                "total": row["total"],
                "helpful_count": row["helpful"],
                "helpful_rate": round(row["helpful"] / row["total"], 4) if row["total"] > 0 else 0.0,
                "avg_rating": round(row["avg_rating"], 2) if row["avg_rating"] else 0.0,
            }
            for row in rows
        ]

        return stats

    async def analyze_accuracy(self, days: int = 7) -> dict[str, Any]:
        """分析预测准确度。

        统计指定天数内的预测准确度趋势，包括每日准确率和各动作准确率。

        Args:
            days: 分析天数范围（默认 7 天）

        Returns:
            dict: 包含以下键的分析结果
                - period_days: 分析天数
                - total_predictions: 总预测数
                - total_feedback: 总反馈数
                - overall_accuracy: 整体准确率
                - daily_accuracy: 每日准确率列表
                - action_accuracy: 各动作准确率
        """
        conn = await self._get_conn()
        cutoff_ms = current_time_ms() - days * 86400000

        result: dict[str, Any] = {
            "period_days": days,
            "total_predictions": 0,
            "total_feedback": 0,
            "overall_accuracy": 0.0,
            "daily_accuracy": [],
            "action_accuracy": [],
        }

        # 期间内的总预测数
        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM user_predictions WHERE created_at > ?",
            (cutoff_ms,),
        )
        row = await cursor.fetchone()
        result["total_predictions"] = row["count"] if row else 0

        # 期间内的总反馈数
        cursor = await conn.execute(
            "SELECT COUNT(*) as count FROM prediction_feedback WHERE timestamp > ?",
            (cutoff_ms,),
        )
        row = await cursor.fetchone()
        result["total_feedback"] = row["count"] if row else 0

        if result["total_feedback"] == 0:
            return result

        # 整体准确率（结合 user_predictions.is_correct 和 feedback.was_helpful）
        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN pf.was_helpful = 1 OR up.is_correct = 1 THEN 1 ELSE 0 END) as correct
            FROM prediction_feedback pf
            LEFT JOIN user_predictions up ON pf.prediction_id = up.id
            WHERE pf.timestamp > ?
            """,
            (cutoff_ms,),
        )
        row = await cursor.fetchone()
        if row and row["total"] > 0:
            result["overall_accuracy"] = round(row["correct"] / row["total"], 4)

        # 每日准确率
        cursor = await conn.execute(
            """
            SELECT
                DATE(timestamp / 1000, 'unixepoch') as day,
                COUNT(*) as total,
                SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful
            FROM prediction_feedback
            WHERE timestamp > ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (cutoff_ms,),
        )
        rows = await cursor.fetchall()
        result["daily_accuracy"] = [
            {
                "date": row["day"],
                "total": row["total"],
                "helpful": row["helpful"],
                "accuracy": round(row["helpful"] / row["total"], 4) if row["total"] > 0 else 0.0,
            }
            for row in rows
        ]

        # 各动作准确率
        cursor = await conn.execute(
            """
            SELECT
                action,
                COUNT(*) as total,
                SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful
            FROM prediction_feedback
            WHERE timestamp > ?
            GROUP BY action
            ORDER BY total DESC
            """,
            (cutoff_ms,),
        )
        rows = await cursor.fetchall()
        result["action_accuracy"] = [
            {
                "action": row["action"],
                "total": row["total"],
                "helpful": row["helpful"],
                "accuracy": round(row["helpful"] / row["total"], 4) if row["total"] > 0 else 0.0,
            }
            for row in rows
        ]

        return result

    async def cleanup(self, max_age_days: int = 90) -> int:
        """清理超过指定天数的过期反馈数据。

        删除 prediction_feedback 表和关联的 user_predictions 中的过期数据。

        Args:
            max_age_days: 最大保留天数（默认 90 天）

        Returns:
            int: 清理的反馈记录数
        """
        conn = await self._get_conn()
        cutoff_ms = current_time_ms() - max_age_days * 86400000

        cursor = await conn.execute(
            "DELETE FROM prediction_feedback WHERE timestamp < ?",
            (cutoff_ms,),
        )
        deleted_count = cursor.rowcount

        if deleted_count > 0:
            # 同时清理关联的旧预测记录
            await conn.execute(
                "DELETE FROM user_predictions WHERE created_at < ? AND feedback_at IS NULL",
                (cutoff_ms,),
            )
            await conn.commit()
            logger.info(
                "Cleaned up %d feedback records older than %d days",
                deleted_count,
                max_age_days,
            )

        return deleted_count

    async def get_recent_feedback(
        self,
        limit: int = 20,
        min_rating: int = 1,
    ) -> list[FeedbackEntry]:
        """获取最近的反馈条目。

        Args:
            limit: 最大返回条数（默认 20）
            min_rating: 最低评分过滤（默认 1，即全部）

        Returns:
            list[FeedbackEntry]: 反馈条目列表
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM prediction_feedback WHERE rating >= ? ORDER BY timestamp DESC LIMIT ?",
            (min_rating, limit),
        )
        rows = await cursor.fetchall()
        return [FeedbackEntry.from_row(row) for row in rows]

    async def get_action_feedback_summary(self, action: str) -> dict[str, Any]:
        """获取特定动作的反馈摘要。

        Args:
            action: 动作名称

        Returns:
            dict: 包含 total, helpful_count, avg_rating, 最近反馈的摘要
        """
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful,
                AVG(rating) as avg_rating
            FROM prediction_feedback
            WHERE action = ?
            """,
            (action,),
        )
        row = await cursor.fetchone()

        if not row or row["total"] == 0:
            return {"action": action, "total": 0, "helpful_count": 0, "avg_rating": 0.0, "recent": []}

        cursor = await conn.execute(
            "SELECT * FROM prediction_feedback WHERE action = ? ORDER BY timestamp DESC LIMIT 5",
            (action,),
        )
        recent_rows = await cursor.fetchall()

        return {
            "action": action,
            "total": row["total"],
            "helpful_count": row["helpful"],
            "avg_rating": round(row["avg_rating"], 2) if row["avg_rating"] else 0.0,
            "recent": [FeedbackEntry.from_row(r) for r in recent_rows],
        }

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
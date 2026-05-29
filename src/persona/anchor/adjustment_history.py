# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""锚点调整历史 — SQLite 持久化。

记录所有锚点调整操作，支持审计、统计、回滚。

表结构：
adjustment_records:
- id: TEXT PK
- anchor_id: TEXT
- trigger_type: TEXT  — USER_FEEDBACK / SELF_REFLECTION / INTERACTION_ACCUMULATION
- adjustment_vector: TEXT(JSON)  — 调整向量
- values_before: TEXT(JSON)  — 调整前价值观
- values_after: TEXT(JSON)  — 调整后价值观
- review_result: TEXT  — APPROVED / MODIFIED / REJECTED
- drift_score_before: REAL
- drift_score_after: REAL
- created_at: TIMESTAMP
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


class TriggerType(str, Enum):
    """调整触发类型"""

    USER_FEEDBACK = "user_feedback"  # 用户反馈
    SELF_REFLECTION = "self_reflection"  # 自我反思
    INTERACTION_ACCUMULATION = "interaction_accumulation"  # 交互积累


class ReviewResult(str, Enum):
    """审查结果"""

    APPROVED = "approved"  # 批准
    MODIFIED = "modified"  # 修改
    REJECTED = "rejected"  # 拒绝


@dataclass
class AdjustmentRecord:
    """调整记录。

    Attributes:
        id: 记录 ID
        anchor_id: 锚点 ID
        trigger_type: 触发类型
        adjustment_vector: 调整向量
        values_before: 调整前价值观
        values_after: 调整后价值观
        review_result: 审查结果
        drift_score_before: 调整前漂移评分
        drift_score_after: 调整后漂移评分
        created_at: 创建时间戳
    """

    id: str
    anchor_id: str
    trigger_type: TriggerType
    adjustment_vector: np.ndarray
    values_before: Dict[str, float]
    values_after: Dict[str, float]
    review_result: Optional[ReviewResult] = None
    drift_score_before: float = 0.0
    drift_score_after: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。

        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "id": self.id,
            "anchor_id": self.anchor_id,
            "trigger_type": self.trigger_type.value,
            "adjustment_vector": self.adjustment_vector.tolist(),
            "values_before": self.values_before,
            "values_after": self.values_after,
            "review_result": self.review_result.value if self.review_result else None,
            "drift_score_before": self.drift_score_before,
            "drift_score_after": self.drift_score_after,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AdjustmentRecord:
        """从字典反序列化。

        Args:
            data: 字典数据

        Returns:
            AdjustmentRecord: 记录实例
        """
        return cls(
            id=data["id"],
            anchor_id=data["anchor_id"],
            trigger_type=TriggerType(data["trigger_type"]),
            adjustment_vector=np.array(data["adjustment_vector"]),
            values_before=data["values_before"],
            values_after=data["values_after"],
            review_result=ReviewResult(data["review_result"])
            if data.get("review_result")
            else None,
            drift_score_before=data.get("drift_score_before", 0.0),
            drift_score_after=data.get("drift_score_after", 0.0),
            created_at=data.get("created_at", time.time()),
        )


class AdjustmentHistory:
    """锚点调整历史管理器。

    SQLite 持久化存储所有调整记录。
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS adjustment_records (
        id TEXT PRIMARY KEY,
        anchor_id TEXT NOT NULL,
        trigger_type TEXT NOT NULL,
        adjustment_vector TEXT NOT NULL,
        values_before TEXT NOT NULL,
        values_after TEXT NOT NULL,
        review_result TEXT,
        drift_score_before REAL DEFAULT 0.0,
        drift_score_after REAL DEFAULT 0.0,
        created_at REAL NOT NULL
    )
    """

    INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_anchor_id ON adjustment_records(anchor_id);
    CREATE INDEX IF NOT EXISTS idx_created_at ON adjustment_records(created_at);
    CREATE INDEX IF NOT EXISTS idx_trigger_type ON adjustment_records(trigger_type);
    """

    def __init__(self, db_path: str = "./data/adjustment_history.db") -> None:
        """初始化历史管理器。

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库。"""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")

        cursor = self._conn.cursor()
        cursor.execute(self.CREATE_TABLE_SQL)
        cursor.execute(self.INDEX_SQL)
        self._conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接。

        Returns:
            sqlite3.Connection: 连接对象
        """
        if self._conn is None:
            self._init_db()
        return self._conn

    def record(
        self,
        anchor_id: str,
        trigger_type: TriggerType,
        adjustment: np.ndarray,
        values_before: Dict[str, float],
        values_after: Dict[str, float],
        review_result: Optional[ReviewResult] = None,
        drift_before: float = 0.0,
        drift_after: float = 0.0,
    ) -> AdjustmentRecord:
        """记录调整。

        Args:
            anchor_id: 锚点 ID
            trigger_type: 触发类型
            adjustment: 调整向量
            values_before: 调整前价值观
            values_after: 调整后价值观
            review_result: 审查结果
            drift_before: 调整前漂移评分
            drift_after: 调整后漂移评分

        Returns:
            AdjustmentRecord: 创建的记录
        """
        record = AdjustmentRecord(
            id=str(uuid.uuid4()),
            anchor_id=anchor_id,
            trigger_type=trigger_type,
            adjustment_vector=adjustment,
            values_before=values_before,
            values_after=values_after,
            review_result=review_result,
            drift_score_before=drift_before,
            drift_score_after=drift_after,
        )

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO adjustment_records
            (id, anchor_id, trigger_type, adjustment_vector, values_before, values_after,
             review_result, drift_score_before, drift_score_after, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.anchor_id,
                record.trigger_type.value,
                json.dumps(record.adjustment_vector.tolist()),
                json.dumps(record.values_before),
                json.dumps(record.values_after),
                record.review_result.value if record.review_result else None,
                record.drift_score_before,
                record.drift_score_after,
                record.created_at,
            ),
        )

        conn.commit()

        return record

    def get_history(
        self,
        anchor_id: str,
        limit: int = 100,
    ) -> List[AdjustmentRecord]:
        """获取历史记录。

        Args:
            anchor_id: 锚点 ID
            limit: 返回数量限制

        Returns:
            List[AdjustmentRecord]: 记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, anchor_id, trigger_type, adjustment_vector, values_before, values_after,
                   review_result, drift_score_before, drift_score_after, created_at
            FROM adjustment_records
            WHERE anchor_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (anchor_id, limit),
        )

        rows = cursor.fetchall()
        records = []

        for row in rows:
            record = AdjustmentRecord(
                id=row[0],
                anchor_id=row[1],
                trigger_type=TriggerType(row[2]),
                adjustment_vector=np.array(json.loads(row[3])),
                values_before=json.loads(row[4]),
                values_after=json.loads(row[5]),
                review_result=ReviewResult(row[6]) if row[6] else None,
                drift_score_before=row[7],
                drift_score_after=row[8],
                created_at=row[9],
            )
            records.append(record)

        return records

    def get_cumulative_adjustment(self, anchor_id: str) -> float:
        """获取累计调整量。

        Args:
            anchor_id: 锚点 ID

        Returns:
            float: 累计调整量（向量范数之和）
        """
        records = self.get_history(anchor_id, limit=1000)

        total = 0.0
        for record in records:
            total += np.linalg.norm(record.adjustment_vector)

        return total

    def get_approval_rate(self, anchor_id: str) -> float:
        """获取批准率。

        Args:
            anchor_id: 锚点 ID

        Returns:
            float: 批准率 (0-1)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN review_result = 'approved' THEN 1 ELSE 0 END) as approved
            FROM adjustment_records
            WHERE anchor_id = ? AND review_result IS NOT NULL
            """,
            (anchor_id,),
        )

        row = cursor.fetchone()

        if row is None or row[0] == 0:
            return 0.0

        return row[1] / row[0]

    def cleanup_old_records(
        self,
        anchor_id: Optional[str] = None,
        max_age_days: int = 90,
    ) -> int:
        """清理旧记录。

        Args:
            anchor_id: 锚点 ID，None 则清理所有
            max_age_days: 最大保留天数

        Returns:
            int: 清理的记录数
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        if anchor_id:
            cursor.execute(
                "SELECT COUNT(*) FROM adjustment_records WHERE anchor_id = ? AND created_at < ?",
                (anchor_id, cutoff_time),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM adjustment_records WHERE created_at < ?",
                (cutoff_time,),
            )

        count = cursor.fetchone()[0]

        if anchor_id:
            cursor.execute(
                "DELETE FROM adjustment_records WHERE anchor_id = ? AND created_at < ?",
                (anchor_id, cutoff_time),
            )
        else:
            cursor.execute(
                "DELETE FROM adjustment_records WHERE created_at < ?",
                (cutoff_time,),
            )

        conn.commit()

        return count

    def get_statistics(self, anchor_id: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息。

        Args:
            anchor_id: 锚点 ID，None 则统计全部

        Returns:
            Dict[str, Any]: 统计信息
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if anchor_id:
            cursor.execute(
                """
                SELECT COUNT(*) as total,
                       AVG(drift_score_after) as avg_drift,
                       MAX(created_at) as last_adjustment
                FROM adjustment_records
                WHERE anchor_id = ?
                """,
                (anchor_id,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) as total,
                       AVG(drift_score_after) as avg_drift,
                       MAX(created_at) as last_adjustment
                FROM adjustment_records
                """
            )

        row = cursor.fetchone()

        # 按触发类型统计
        if anchor_id:
            cursor.execute(
                """
                SELECT trigger_type, COUNT(*) as count
                FROM adjustment_records
                WHERE anchor_id = ?
                GROUP BY trigger_type
                """,
                (anchor_id,),
            )
        else:
            cursor.execute(
                """
                SELECT trigger_type, COUNT(*) as count
                FROM adjustment_records
                GROUP BY trigger_type
                """
            )

        type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 按审查结果统计
        if anchor_id:
            cursor.execute(
                """
                SELECT review_result, COUNT(*) as count
                FROM adjustment_records
                WHERE anchor_id = ? AND review_result IS NOT NULL
                GROUP BY review_result
                """,
                (anchor_id,),
            )
        else:
            cursor.execute(
                """
                SELECT review_result, COUNT(*) as count
                FROM adjustment_records
                WHERE review_result IS NOT NULL
                GROUP BY review_result
                """
            )

        result_counts = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total_records": row[0],
            "average_drift_score": row[1] or 0.0,
            "last_adjustment_time": row[2],
            "by_trigger_type": type_counts,
            "by_review_result": result_counts,
        }

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        """析构函数。"""
        self.close()

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""价值观↔向量双向映射。

实现：
- 正向映射：向量→价值观
- 反向映射：价值观调整→向量微调
- 安全限制：单次/累计调整幅度限制、漂移评分上限
- 回滚支持：快照保存与恢复
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .value_dimensions import ValueDimensionsRegistry


# 安全限制常量
MAX_SINGLE_ADJUSTMENT = 0.05  # 单次调整最大幅度
MAX_CUMULATIVE_ADJUSTMENT = 0.15  # 累计调整最大幅度
MAX_DRIFT_SCORE = 0.25  # 漂移评分上限（超过则拒绝调整）


@dataclass
class AdjustmentSnapshot:
    """调整快照。

    Attributes:
        snapshot_id: 快照 ID
        anchor_id: 锚点 ID
        vector: 调整前向量
        values: 调整前价值观
        timestamp: 时间戳
        metadata: 元数据
    """

    snapshot_id: str
    anchor_id: str
    vector: np.ndarray
    values: Dict[str, float]
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。

        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "snapshot_id": self.snapshot_id,
            "anchor_id": self.anchor_id,
            "vector": self.vector.tolist(),
            "values": self.values,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AdjustmentSnapshot:
        """从字典反序列化。

        Args:
            data: 字典数据

        Returns:
            AdjustmentSnapshot: 快照实例
        """
        return cls(
            snapshot_id=data["snapshot_id"],
            anchor_id=data["anchor_id"],
            vector=np.array(data["vector"]),
            values=data["values"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AdjustmentResult:
    """调整结果。

    Attributes:
        success: 是否成功
        adjusted_vector: 调整后的向量
        adjusted_values: 调整后的价值观
        drift_score: 漂移评分
        rejection_reason: 拒绝原因（如有）
        snapshot_id: 快照 ID
    """

    success: bool
    adjusted_vector: Optional[np.ndarray] = None
    adjusted_values: Optional[Dict[str, float]] = None
    drift_score: float = 0.0
    rejection_reason: Optional[str] = None
    snapshot_id: Optional[str] = None


class BidirectionalMapper:
    """价值观↔向量双向映射器。

    正向映射：将 128 维风格向量 +256 维决策向量映射到 25 维价值观空间
    反向映射：将价值观的变化量反向传播到向量空间

    安全限制：
    - MAX_SINGLE_ADJUSTMENT = 0.05  — 单次调整最大幅度
    - MAX_CUMULATIVE_ADJUSTMENT = 0.15  — 累计调整最大幅度
    - MAX_DRIFT_SCORE = 0.25  — 漂移评分上限（超过则拒绝调整）

    回滚支持：
    - 每次调整前保存快照
    - rollback(snapshot_id) 可恢复
    """

    def __init__(self, style_dim: int = 128, decision_dim: int = 256) -> None:
        """初始化双向映射器。

        Args:
            style_dim: 风格向量维度
            decision_dim: 决策向量维度
        """
        self.style_dim = style_dim
        self.decision_dim = decision_dim
        self.registry = ValueDimensionsRegistry()

        # 投影矩阵（随机初始化，可通过训练优化）
        self._projection_matrix: Optional[np.ndarray] = None
        self._pseudo_inverse: Optional[np.ndarray] = None

        # 快照存储
        self._snapshots: Dict[str, AdjustmentSnapshot] = {}

        # 累计调整跟踪
        self._cumulative_adjustments: Dict[str, float] = {}

    def _get_projection_matrix(self) -> np.ndarray:
        """获取投影矩阵（懒加载）。

        Returns:
            np.ndarray: (25, 384) 投影矩阵
        """
        if self._projection_matrix is None:
            # 初始化随机投影矩阵
            np.random.seed(42)
            combined_dim = self.style_dim + self.decision_dim
            self._projection_matrix = np.random.randn(25, combined_dim).astype(np.float32) * 0.01

        return self._projection_matrix

    def _get_pseudo_inverse(self) -> np.ndarray:
        """获取伪逆矩阵（懒加载）。

        Returns:
            np.ndarray: (384, 25) 伪逆矩阵
        """
        if self._pseudo_inverse is None:
            proj_matrix = self._get_projection_matrix()
            # 计算 Moore-Penrose 伪逆
            self._pseudo_inverse = np.linalg.pinv(proj_matrix)

        return self._pseudo_inverse

    def map_vector_to_values(
        self,
        style_vector: np.ndarray,
        decision_vector: np.ndarray,
    ) -> Dict[str, float]:
        """正向映射：向量→价值观。

        将 128 维风格向量 +256 维决策向量映射到 25 维价值观空间

        Args:
            style_vector: 128 维风格向量
            decision_vector: 256 维决策向量

        Returns:
            Dict[str, float]: 25 维价值观评分 {维度名：评分}
        """
        # 验证维度
        if len(style_vector) != self.style_dim:
            raise ValueError(
                f"Style vector dimension mismatch: expected {self.style_dim}, got {len(style_vector)}"
            )
        if len(decision_vector) != self.decision_dim:
            raise ValueError(
                f"Decision vector dimension mismatch: expected {self.decision_dim}, got {len(decision_vector)}"
            )

        # 拼接向量
        combined_vector = np.concatenate([style_vector, decision_vector])

        # 投影到价值观空间
        proj_matrix = self._get_projection_matrix()
        values_raw = np.dot(proj_matrix, combined_vector)

        # Sigmoid 激活到 (0, 1) 区间
        values_scaled = 1 / (1 + np.exp(-values_raw))

        # 转换为字典
        dimensions = self.registry.get_all_dimensions()
        values_dict = {}

        for i, dim in enumerate(dimensions):
            if i < len(values_scaled):
                # 应用范围约束
                value = max(dim.min_value, min(dim.max_value, values_scaled[i]))
                values_dict[dim.name] = value
            else:
                values_dict[dim.name] = dim.default_value

        return values_dict

    def map_values_to_adjustment(
        self,
        current_values: Dict[str, float],
        target_values: Dict[str, float],
        current_vector: np.ndarray,
    ) -> np.ndarray:
        """反向映射：价值观调整→向量微调。

        将价值观的变化量反向传播到向量空间

        Args:
            current_values: 当前价值观
            target_values: 目标价值观
            current_vector: 当前向量

        Returns:
            np.ndarray: 向量调整量
        """
        # 计算价值观变化量
        delta_values = np.zeros(25, dtype=np.float32)
        dimensions = self.registry.get_all_dimensions()

        for i, dim in enumerate(dimensions):
            current = current_values.get(dim.name, dim.default_value)
            target = target_values.get(dim.name, dim.default_value)
            delta = target - current

            # 限制单次变化幅度
            delta = np.clip(delta, -MAX_SINGLE_ADJUSTMENT, MAX_SINGLE_ADJUSTMENT)
            delta_values[i] = delta

        # 使用伪逆矩阵反向投影
        pseudo_inv = self._get_pseudo_inverse()
        delta_vector = np.dot(pseudo_inv, delta_values)

        # 限制调整幅度
        norm = np.linalg.norm(delta_vector)
        if norm > MAX_SINGLE_ADJUSTMENT:
            delta_vector = delta_vector * (MAX_SINGLE_ADJUSTMENT / norm)

        return delta_vector

    def apply_adjustment(
        self,
        anchor_vector: np.ndarray,
        adjustment: np.ndarray,
        anchor_id: str = "unknown",
    ) -> Tuple[np.ndarray, AdjustmentResult]:
        """应用向量调整。

        Args:
            anchor_vector: 锚点向量
            adjustment: 调整向量
            anchor_id: 锚点 ID

        Returns:
            Tuple[np.ndarray, AdjustmentResult]: (调整后的向量，调整结果)
        """
        # 创建快照
        snapshot_id = self.create_snapshot(anchor_vector, {})

        # 计算累计调整
        cumulative = self._cumulative_adjustments.get(anchor_id, 0.0)
        adjustment_norm = np.linalg.norm(adjustment)

        # 检查累计调整限制
        if cumulative + adjustment_norm > MAX_CUMULATIVE_ADJUSTMENT:
            result = AdjustmentResult(
                success=False,
                drift_score=cumulative + adjustment_norm,
                rejection_reason=f"Cumulative adjustment ({cumulative + adjustment_norm:.3f}) exceeds limit ({MAX_CUMULATIVE_ADJUSTMENT})",
                snapshot_id=snapshot_id,
            )
            return anchor_vector, result

        # 应用调整
        adjusted_vector = anchor_vector + adjustment

        # L2 归一化
        norm = np.linalg.norm(adjusted_vector)
        if norm > 0:
            adjusted_vector = adjusted_vector / norm

        # 计算漂移评分
        drift_score = np.linalg.norm(adjustment)

        # 更新累计调整
        self._cumulative_adjustments[anchor_id] = cumulative + adjustment_norm

        # 检查漂移限制
        if drift_score > MAX_DRIFT_SCORE:
            # 回滚
            self.rollback(snapshot_id)

            result = AdjustmentResult(
                success=False,
                drift_score=drift_score,
                rejection_reason=f"Drift score ({drift_score:.3f}) exceeds limit ({MAX_DRIFT_SCORE})",
                snapshot_id=snapshot_id,
            )
            return anchor_vector, result

        result = AdjustmentResult(
            success=True,
            adjusted_vector=adjusted_vector,
            drift_score=drift_score,
            snapshot_id=snapshot_id,
        )

        return adjusted_vector, result

    def validate_adjustment(self, adjustment: np.ndarray, cumulative: float) -> bool:
        """验证调整是否合法。

        Args:
            adjustment: 调整向量
            cumulative: 当前累计调整量

        Returns:
            bool: 是否合法
        """
        adjustment_norm = np.linalg.norm(adjustment)

        # 检查单次调整限制
        if adjustment_norm > MAX_SINGLE_ADJUSTMENT:
            return False

        # 检查累计调整限制
        if cumulative + adjustment_norm > MAX_CUMULATIVE_ADJUSTMENT:
            return False

        return True

    def create_snapshot(self, vector: np.ndarray, values: Dict[str, float]) -> str:
        """创建快照。

        Args:
            vector: 当前向量
            values: 当前价值观

        Returns:
            str: 快照 ID
        """
        snapshot_id = hashlib.sha256(f"{time.time()}_{np.sum(vector):.6f}".encode()).hexdigest()[
            :16
        ]

        snapshot = AdjustmentSnapshot(
            snapshot_id=snapshot_id,
            anchor_id="unknown",
            vector=vector.copy(),
            values=values.copy(),
        )

        self._snapshots[snapshot_id] = snapshot

        return snapshot_id

    def rollback(self, snapshot_id: str) -> Tuple[np.ndarray, Dict[str, float]]:
        """回滚到指定快照。

        Args:
            snapshot_id: 快照 ID

        Returns:
            Tuple[np.ndarray, Dict[str, float]]: (回滚后的向量，价值观)

        Raises:
            KeyError: 快照不存在
        """
        if snapshot_id not in self._snapshots:
            raise KeyError(f"Snapshot {snapshot_id} not found")

        snapshot = self._snapshots[snapshot_id]

        # 恢复向量和价值观
        restored_vector = snapshot.vector.copy()
        restored_values = snapshot.values.copy()

        return restored_vector, restored_values

    def get_snapshot(self, snapshot_id: str) -> Optional[AdjustmentSnapshot]:
        """获取快照。

        Args:
            snapshot_id: 快照 ID

        Returns:
            Optional[AdjustmentSnapshot]: 快照，不存在则返回 None
        """
        return self._snapshots.get(snapshot_id)

    def clear_snapshots(self, older_than: Optional[float] = None) -> int:
        """清理快照。

        Args:
            older_than: 清理早于此时间戳的快照，None 则清理全部

        Returns:
            int: 清理的快照数
        """
        if older_than is None:
            count = len(self._snapshots)
            self._snapshots.clear()
            return count

        count = 0
        to_remove = []

        for snapshot_id, snapshot in self._snapshots.items():
            if snapshot.timestamp < older_than:
                to_remove.append(snapshot_id)
                count += 1

        for snapshot_id in to_remove:
            del self._snapshots[snapshot_id]

        return count

    def get_cumulative_adjustment(self, anchor_id: str) -> float:
        """获取累计调整量。

        Args:
            anchor_id: 锚点 ID

        Returns:
            float: 累计调整量
        """
        return self._cumulative_adjustments.get(anchor_id, 0.0)

    def reset_cumulative_adjustment(self, anchor_id: str) -> None:
        """重置累计调整量。

        Args:
            anchor_id: 锚点 ID
        """
        self._cumulative_adjustments[anchor_id] = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。

        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "style_dim": self.style_dim,
            "decision_dim": self.decision_dim,
            "num_snapshots": len(self._snapshots),
            "cumulative_adjustments": self._cumulative_adjustments.copy(),
            "max_single_adjustment": MAX_SINGLE_ADJUSTMENT,
            "max_cumulative_adjustment": MAX_CUMULATIVE_ADJUSTMENT,
            "max_drift_score": MAX_DRIFT_SCORE,
        }

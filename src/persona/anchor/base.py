# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""决策锚点系统基础定义。

包含：枚举类、配置类、锚点基类、版本管理、相似度计算等核心组件。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

import numpy as np


class DriftLevel(Enum):
    """漂移等级 5 级"""

    NONE = 0  # 无漂移
    MILD = 1  # 轻微漂移
    MODERATE = 2  # 中度漂移
    SIGNIFICANT = 3  # 显著漂移
    CRITICAL = 4  # 严重漂移


class AnchorType(Enum):
    """锚点类型"""

    DECISION = "decision"  # 决策锚点
    STYLE = "style"  # 风格锚点
    COMBINED = "combined"  # 组合锚点


class AnchorStatus(Enum):
    """锚点状态"""

    ACTIVE = "active"  # 激活
    INACTIVE = "inactive"  # 未激活
    DRAFT = "draft"  # 草稿
    ARCHIVED = "archived"  # 归档


@dataclass
class AnchorConfig:
    """锚点配置类。

    Attributes:
        decision_dim: 决策锚点维度，默认 256
        style_dim: 风格锚点维度，默认 128
        text_encoder_name: 文本编码器名称
        num_priority_bins: 优先级分箱数
        use_projection_head: 是否使用投影头
        dropout: dropout 率
        similarity_threshold: 相似度阈值
        version_storage_path: 版本存储路径
        max_versions: 最大版本数
        drift_significance_threshold: 漂移显著性阈值
        drift_window_size: 漂移检测窗口大小
        drift_min_samples: 最小样本数
    """

    decision_dim: int = 256
    style_dim: int = 128
    text_encoder_name: str = "bert-base-chinese"
    num_priority_bins: int = 10
    use_projection_head: bool = True
    dropout: float = 0.1
    similarity_threshold: float = 0.85
    version_storage_path: str = "./anchor_versions"
    max_versions: int = 10
    drift_significance_threshold: float = 0.05
    drift_window_size: int = 100
    drift_min_samples: int = 50


@dataclass
class AnchorBase:
    """锚点基类。

    Attributes:
        anchor_id: 锚点 ID
        anchor_type: 锚点类型
        vector: 锚点向量
        created_at: 创建时间戳
        updated_at: 更新时间戳
        status: 锚点状态
        metadata: 元数据
    """

    anchor_id: str
    anchor_type: AnchorType
    vector: np.ndarray
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: AnchorStatus = AnchorStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> np.ndarray:
        """L2 归一化向量。

        Returns:
            np.ndarray: 归一化后的向量
        """
        norm = np.linalg.norm(self.vector)
        if norm > 0:
            return self.vector / norm
        return self.vector

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。

        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "anchor_id": self.anchor_id,
            "anchor_type": self.anchor_type.value,
            "vector": self.vector.tolist(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AnchorBase:
        """从字典反序列化。

        Args:
            data: 字典数据

        Returns:
            AnchorBase: 锚点实例
        """
        return cls(
            anchor_id=data["anchor_id"],
            anchor_type=AnchorType(data["anchor_type"]),
            vector=np.array(data["vector"]),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            status=AnchorStatus(data.get("status", "active")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DecisionAnchor(AnchorBase):
    """决策锚点。

    Attributes:
        user_goal: 用户目标
        priorities: 优先级列表
        constraints: 约束条件
    """

    user_goal: str = ""
    priorities: List[Dict[str, float]] = field(default_factory=list)
    constraints: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """后处理：设置锚点类型"""
        self.anchor_type = AnchorType.DECISION


@dataclass
class StyleAnchor(AnchorBase):
    """风格锚点。

    Attributes:
        style_features: 风格特征
        source_texts: 源文本列表
    """

    style_features: Dict[str, Any] = field(default_factory=dict)
    source_texts: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """后处理：设置锚点类型"""
        self.anchor_type = AnchorType.STYLE


@dataclass
class AnchorVersion:
    """锚点版本。

    Attributes:
        version_id: 版本 ID
        decision_vector: 决策向量
        style_vector: 风格向量
        sample_count: 样本数
        performance_score: 性能评分
        is_active: 是否激活
        metadata: 元数据
    """

    version_id: str
    decision_vector: np.ndarray
    style_vector: np.ndarray
    sample_count: int = 0
    performance_score: float = 0.0
    is_active: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def combined_vector(self) -> np.ndarray:
        """拼接决策和风格向量。

        Returns:
            np.ndarray: 拼接后的向量
        """
        return np.concatenate([self.decision_vector, self.style_vector])

    def generate_version_id(self) -> str:
        """基于向量内容生成版本 ID。

        Returns:
            str: SHA256 哈希 ID
        """
        content = {
            "decision": self.decision_vector.tolist()[:10],
            "style": self.style_vector.tolist()[:10],
            "sample_count": self.sample_count,
        }
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]


class SimilarityCalculator:
    """相似度计算器。"""

    @staticmethod
    def cosine(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """余弦相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B

        Returns:
            float: 余弦相似度 (0-1)
        """
        dot_product = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        if norm_a > 0 and norm_b > 0:
            return dot_product / (norm_a * norm_b)
        return 0.0

    @staticmethod
    def euclidean(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """归一化欧氏距离相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B

        Returns:
            float: 相似度 (0-1)
        """
        distance = np.linalg.norm(vec_a - vec_b)
        max_distance = np.sqrt(len(vec_a))
        return 1.0 - (distance / max_distance) if max_distance > 0 else 1.0

    @staticmethod
    def dot_product(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """点积相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B

        Returns:
            float: 点积值
        """
        return float(np.dot(vec_a, vec_b))

    @classmethod
    def compute(cls, vec_a: np.ndarray, vec_b: np.ndarray, method: str = "cosine") -> float:
        """计算相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B
            method: 方法 (cosine/euclidean/dot)

        Returns:
            float: 相似度值
        """
        if method == "cosine":
            return cls.cosine(vec_a, vec_b)
        elif method == "euclidean":
            return cls.euclidean(vec_a, vec_b)
        elif method == "dot":
            return cls.dot_product(vec_a, vec_b)
        else:
            raise ValueError(f"Unknown similarity method: {method}")


def generate_anchor_id(prefix: str = "anchor", **kwargs: Any) -> str:
    """生成锚点 ID。

    Args:
        prefix: ID 前缀
        **kwargs: 用于生成哈希的内容

    Returns:
        str: 锚点 ID
    """
    content = {
        "prefix": prefix,
        "timestamp": time.time(),
        **kwargs,
    }
    content_str = json.dumps(content, sort_keys=True, default=str)
    hash_id = hashlib.sha256(content_str.encode()).hexdigest()[:12]
    return f"{prefix}_{hash_id}"


def validate_vector_dimension(vector: np.ndarray, expected_dim: int, name: str = "vector") -> bool:
    """验证向量维度。

    Args:
        vector: 待验证向量
        expected_dim: 期望维度
        name: 向量名称

    Returns:
        bool: 是否有效

    Raises:
        ValueError: 维度不匹配
    """
    if vector.ndim != 1:
        raise ValueError(f"{name} must be 1D, got {vector.ndim}D")

    if len(vector) != expected_dim:
        raise ValueError(f"{name} dimension mismatch: expected {expected_dim}, got {len(vector)}")

    return True

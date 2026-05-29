# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""锚点版本管理与相似度服务。

包含：Wasserstein 漂移检测器、锚点版本管理器、锚点相似度计算服务。
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from .base import (
    AnchorType,
    AnchorVersion,
    DriftLevel,
    SimilarityCalculator,
    StyleAnchor,
)


@dataclass
class FeedbackSample:
    """反馈样本。

    Attributes:
        score: 评分 (0-1)
        timestamp: 时间戳
        metadata: 元数据
    """

    score: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WassersteinDriftDetector:
    """基于 Wasserstein 距离的偏好漂移检测器。

    使用 1-Wasserstein 距离（Earth Mover's Distance 的特例）检测用户反馈分布的漂移。
    """

    def __init__(self, window_size: int = 100, min_samples: int = 50) -> None:
        """初始化漂移检测器。

        Args:
            window_size: 滑动窗口大小
            min_samples: 最小样本数
        """
        self.window_size = window_size
        self.min_samples = min_samples
        self._feedback_window: Deque[FeedbackSample] = deque(maxlen=window_size)

    def add_feedback(self, feedback: FeedbackSample) -> None:
        """添加反馈样本。

        Args:
            feedback: 反馈样本
        """
        self._feedback_window.append(feedback)

    def compute_wasserstein_distance(self, samples_a: List[float], samples_b: List[float]) -> float:
        """计算 1-Wasserstein 距离。

        Args:
            samples_a: 样本集 A
            samples_b: 样本集 B

        Returns:
            float: Wasserstein 距离
        """
        if not samples_a or not samples_b:
            return 0.0

        # 排序后取均值绝对差
        sorted_a = sorted(samples_a)
        sorted_b = sorted(samples_b)

        # 对齐长度
        min_len = min(len(sorted_a), len(sorted_b))
        sorted_a = sorted_a[:min_len]
        sorted_b = sorted_b[:min_len]

        # 计算距离
        distance = np.mean(np.abs(np.array(sorted_a) - np.array(sorted_b)))

        return distance

    def permutation_test(
        self, samples_a: List[float], samples_b: List[float], num_permutations: int = 1000
    ) -> float:
        """排列检验计算 p 值。

        Args:
            samples_a: 样本集 A
            samples_b: 样本集 B
            num_permutations: 排列次数

        Returns:
            float: p 值
        """
        if not samples_a or not samples_b:
            return 1.0

        observed_distance = self.compute_wasserstein_distance(samples_a, samples_b)

        # 合并样本
        combined = samples_a + samples_b
        n_a = len(samples_a)

        # 排列检验
        count = 0
        for _ in range(num_permutations):
            random.shuffle(combined)
            perm_a = combined[:n_a]
            perm_b = combined[n_a:]
            perm_distance = self.compute_wasserstein_distance(perm_a, perm_b)

            if perm_distance >= observed_distance:
                count += 1

        p_value = count / num_permutations
        return p_value

    def detect_drift(
        self,
        recent_feedback: List[FeedbackSample],
        anchor_version: AnchorVersion,
    ) -> Tuple[DriftLevel, float, float]:
        """检测漂移。

        Args:
            recent_feedback: 最近反馈列表
            anchor_version: 锚点版本

        Returns:
            Tuple[DriftLevel, float, float]: (漂移等级，Wasserstein 距离，p 值)
        """
        if len(self._feedback_window) < self.min_samples or len(recent_feedback) < self.min_samples:
            return DriftLevel.NONE, 0.0, 1.0

        # 历史反馈分数
        historical_scores = [fb.score for fb in self._feedback_window]

        # 最近反馈分数
        recent_scores = [fb.score for fb in recent_feedback]

        # 计算 Wasserstein 距离
        distance = self.compute_wasserstein_distance(historical_scores, recent_scores)

        # 排列检验
        p_value = self.permutation_test(historical_scores, recent_scores)

        # 判定漂移等级
        if p_value > 0.1:
            drift_level = DriftLevel.NONE
        elif p_value > 0.05:
            drift_level = DriftLevel.MILD
        elif p_value > 0.01:
            drift_level = DriftLevel.MODERATE
        else:
            drift_level = DriftLevel.SIGNIFICANT

        return drift_level, distance, p_value

    def clear(self) -> None:
        """清空反馈窗口。"""
        self._feedback_window.clear()


class AnchorVersionManager:
    """锚点版本管理器。

    负责：
    - 创建新版本
    - 激活版本（支持平滑过渡）
    - 混合版本（指数平滑）
    - 回滚
    """

    def __init__(self, max_versions: int = 10, smooth_beta: float = 0.1) -> None:
        """初始化版本管理器。

        Args:
            max_versions: 最大版本数
            smooth_beta: 平滑过渡系数 (0-1)
        """
        self.max_versions = max_versions
        self.smooth_beta = smooth_beta
        self._versions: Dict[str, AnchorVersion] = {}
        self._active_version_id: Optional[str] = None
        self._target_version_id: Optional[str] = None
        self._transition_progress: float = 0.0  # 0 → 1
        self._version_history: List[str] = []

    def create_new_version(
        self,
        decision_vector: np.ndarray,
        style_vector: np.ndarray,
        sample_count: int = 0,
        performance_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AnchorVersion:
        """创建新版本。

        Args:
            decision_vector: 决策向量
            style_vector: 风格向量
            sample_count: 样本数
            performance_score: 性能评分
            metadata: 元数据

        Returns:
            AnchorVersion: 创建的版本
        """
        version = AnchorVersion(
            version_id="",
            decision_vector=decision_vector,
            style_vector=style_vector,
            sample_count=sample_count,
            performance_score=performance_score,
            is_active=False,
            metadata=metadata or {},
        )
        version.version_id = version.generate_version_id()

        self._versions[version.version_id] = version
        self._version_history.append(version.version_id)

        # 清理旧版本
        if len(self._version_history) > self.max_versions:
            old_id = self._version_history.pop(0)
            if old_id in self._versions:
                del self._versions[old_id]

        return version

    def get_active_version(self) -> Optional[AnchorVersion]:
        """获取当前激活版本。

        Returns:
            Optional[AnchorVersion]: 激活版本，如果在过渡中返回混合版本
        """
        if self._target_version_id is not None and self._transition_progress < 1.0:
            # 在过渡中，返回混合版本
            return self._get_blended_version()

        if self._active_version_id is None:
            return None

        return self._versions.get(self._active_version_id)

    def _get_blended_version(self) -> Optional[AnchorVersion]:
        """获取混合版本（指数平滑）。

        Returns:
            Optional[AnchorVersion]: 混合版本
        """
        if self._active_version_id is None or self._target_version_id is None:
            return None

        active = self._versions.get(self._active_version_id)
        target = self._versions.get(self._target_version_id)

        if active is None or target is None:
            return None

        # blended = (1-beta)*active + beta*target
        beta = self.smooth_beta * self._transition_progress
        blended_decision = (1 - beta) * active.decision_vector + beta * target.decision_vector
        blended_style = (1 - beta) * active.style_vector + beta * target.style_vector

        blended = AnchorVersion(
            version_id=f"blended_{active.version_id[:8]}_{target.version_id[:8]}",
            decision_vector=blended_decision,
            style_vector=blended_style,
            sample_count=active.sample_count + target.sample_count,
            performance_score=(active.performance_score + target.performance_score) / 2,
            is_active=True,
            metadata={"blended": True, "progress": self._transition_progress},
        )

        return blended

    def check_and_update(
        self,
        recent_feedback: List[FeedbackSample],
        min_samples: int = 50,
    ) -> Tuple[bool, Optional[AnchorVersion]]:
        """检测漂移并在需要时创建新版本。

        Args:
            recent_feedback: 最近反馈列表
            min_samples: 最小样本数

        Returns:
            Tuple[bool, Optional[AnchorVersion]]: (是否创建新版本，新版本)
        """
        if len(recent_feedback) < min_samples:
            return False, None

        active_version = self.get_active_version()
        if active_version is None:
            return False, None

        detector = WassersteinDriftDetector(min_samples=min_samples)
        for fb in recent_feedback:
            detector.add_feedback(fb)

        drift_level, distance, p_value = detector.detect_drift(recent_feedback, active_version)

        # MODERATE 以上创建新版本
        if drift_level in (DriftLevel.MODERATE, DriftLevel.SIGNIFICANT, DriftLevel.CRITICAL):
            new_version = self.create_new_version(
                decision_vector=active_version.decision_vector * 0.9,
                style_vector=active_version.style_vector * 0.9,
                sample_count=len(recent_feedback),
                performance_score=sum(fb.score for fb in recent_feedback) / len(recent_feedback),
                metadata={
                    "trigger": "drift",
                    "drift_level": drift_level.value,
                    "distance": distance,
                },
            )

            self.activate_version(new_version.version_id, smooth_transition=True)

            return True, new_version

        return False, None

    def activate_version(self, version_id: str, smooth_transition: bool = True) -> bool:
        """激活版本。

        Args:
            version_id: 版本 ID
            smooth_transition: 是否平滑过渡

        Returns:
            bool: 是否成功
        """
        if version_id not in self._versions:
            return False

        if smooth_transition:
            self._target_version_id = version_id
            self._transition_progress = 0.0
        else:
            if self._active_version_id:
                self._versions[self._active_version_id].is_active = False

            self._active_version_id = version_id
            self._target_version_id = None
            self._transition_progress = 1.0
            self._versions[version_id].is_active = True

        return True

    def update_transition(self, step_size: float = 0.01) -> float:
        """更新过渡进度。

        Args:
            step_size: 每步进度增量

        Returns:
            float: 当前进度 (0-1)
        """
        if self._target_version_id is None:
            return 1.0

        self._transition_progress = min(1.0, self._transition_progress + step_size)

        if self._transition_progress >= 1.0:
            # 过渡完成
            if self._active_version_id:
                self._versions[self._active_version_id].is_active = False

            self._active_version_id = self._target_version_id
            self._versions[self._active_version_id].is_active = True
            self._target_version_id = None

        return self._transition_progress

    def rollback_to_version(self, version_id: str) -> bool:
        """回滚到指定版本。

        Args:
            version_id: 版本 ID

        Returns:
            bool: 是否成功
        """
        if version_id not in self._versions:
            return False

        if self._active_version_id:
            self._versions[self._active_version_id].is_active = False

        self._active_version_id = version_id
        self._target_version_id = None
        self._transition_progress = 1.0
        self._versions[version_id].is_active = True

        return True

    def _cleanup_old_versions(self) -> int:
        """清理旧版本。

        Returns:
            int: 清理的版本数
        """
        count = 0
        while len(self._version_history) > self.max_versions:
            old_id = self._version_history.pop(0)
            if old_id in self._versions and not self._versions[old_id].is_active:
                del self._versions[old_id]
                count += 1

        return count


class AnchorSimilarityService:
    """锚点相似度计算服务。"""

    def __init__(self, default_method: str = "cosine") -> None:
        """初始化相似度服务。

        Args:
            default_method: 默认相似度计算方法
        """
        self.default_method = default_method

    def compute_similarity(
        self,
        vec_a: np.ndarray,
        vec_b: np.ndarray,
        method: Optional[str] = None,
    ) -> float:
        """计算两个向量的相似度。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B
            method: 方法 (None 则使用默认)

        Returns:
            float: 相似度值
        """
        method = method or self.default_method
        return SimilarityCalculator.compute(vec_a, vec_b, method)

    def batch_compute_similarity(
        self,
        query: np.ndarray,
        targets: List[np.ndarray],
        method: Optional[str] = None,
    ) -> List[float]:
        """批量计算相似度。

        Args:
            query: 查询向量
            targets: 目标向量列表
            method: 方法

        Returns:
            List[float]: 相似度列表
        """
        return [self.compute_similarity(query, target, method) for target in targets]

    def find_most_similar(
        self,
        query: np.ndarray,
        targets: List[np.ndarray],
        top_k: int = 5,
        method: Optional[str] = None,
        threshold: float = 0.0,
    ) -> List[Tuple[int, float]]:
        """查找最相似的向量。

        Args:
            query: 查询向量
            targets: 目标向量列表
            top_k: 返回前 K 个
            method: 方法
            threshold: 相似度阈值

        Returns:
            List[Tuple[int, float]]: (索引，相似度) 列表
        """
        similarities = self.batch_compute_similarity(query, targets, method)

        # 过滤阈值
        filtered = [(i, sim) for i, sim in enumerate(similarities) if sim >= threshold]

        # 排序
        filtered.sort(key=lambda x: x[1], reverse=True)

        return filtered[:top_k]

    def compute_anchor_similarity(
        self,
        anchor1: StyleAnchor,
        anchor2: StyleAnchor,
        decision_weight: float = 0.5,
    ) -> Dict[str, float]:
        """计算两个锚点的相似度。

        Args:
            anchor1: 锚点 1
            anchor2: 锚点 2
            decision_weight: 决策向量权重

        Returns:
            Dict[str, float]: {decision_similarity, style_similarity, combined_similarity}
        """
        if (
            anchor1.anchor_type == AnchorType.DECISION
            and anchor2.anchor_type == AnchorType.DECISION
        ):
            decision_sim = self.compute_similarity(anchor1.vector, anchor2.vector)
            return {
                "decision_similarity": decision_sim,
                "style_similarity": 0.0,
                "combined_similarity": decision_sim,
            }

        if anchor1.anchor_type == AnchorType.STYLE and anchor2.anchor_type == AnchorType.STYLE:
            style_sim = self.compute_similarity(anchor1.vector, anchor2.vector)
            return {
                "decision_similarity": 0.0,
                "style_similarity": style_sim,
                "combined_similarity": style_sim,
            }

        # 组合锚点
        decision_sim = self.compute_similarity(anchor1.vector, anchor2.vector)
        style_sim = decision_sim

        combined_sim = decision_weight * decision_sim + (1 - decision_weight) * style_sim

        return {
            "decision_similarity": decision_sim,
            "style_similarity": style_sim,
            "combined_similarity": combined_sim,
        }


# 向后兼容别名 — 文档中引用为 AnchorManager，实际类名为 AnchorVersionManager
AnchorManager = AnchorVersionManager

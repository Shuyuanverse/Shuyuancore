# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""风格约束编码。

将风格维度转换为约束向量，用于引导生成
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StyleConstraint:
    """风格约束
    
    Attributes:
        dimension: 维度名称
        target_value: 目标值
        weight: 权重
        tolerance: 容差
    """
    
    dimension: str
    target_value: float
    weight: float = 1.0
    tolerance: float = 0.1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "dimension": self.dimension,
            "target_value": self.target_value,
            "weight": self.weight,
            "tolerance": self.tolerance,
        }


class StyleConstraintEncoder:
    """风格约束编码器
    
    将风格维度转换为约束向量，用于引导生成
    
    编码逻辑：
    1. 从 7 维风格画像提取约束
    2. 每个维度生成 target_value ± tolerance
    3. 应用权重
    4. 输出约束向量
    """
    
    def __init__(self):
        """初始化风格约束编码器"""
        logger.info("[style_constraint] 风格约束编码器初始化完成")
    
    def encode(
        self,
        style_dimensions: Dict[str, Any],
        weights: Optional[Dict[str, float]] = None,
    ) -> List[StyleConstraint]:
        """编码风格约束
        
        Args:
            style_dimensions: 风格维度
            weights: 权重字典（可选）
        
        Returns:
            List[StyleConstraint]: 约束列表
        """
        constraints = []
        
        # 默认权重
        if weights is None:
            weights = {
                "colloquial": 1.0,
                "formal": 1.0,
                "emotional": 0.8,
                "interactive": 0.9,
                "logical": 1.0,
                "concise": 0.7,
                "expressive": 0.8,
            }
        
        # 为每个维度生成约束
        for dim_name, value in style_dimensions.items():
            if dim_name in weights:
                constraint = StyleConstraint(
                    dimension=dim_name,
                    target_value=float(value),
                    weight=weights[dim_name],
                    tolerance=0.1,  # 10% 容差
                )
                constraints.append(constraint)
        
        logger.info(
            "[style_constraint] 编码完成：constraints=%d",
            len(constraints),
        )
        
        return constraints
    
    def to_vector(
        self,
        constraints: List[StyleConstraint],
        target_dim: int = 128,
    ) -> np.ndarray:
        """转换为约束向量
        
        Args:
            constraints: 约束列表
            target_dim: 目标维度
        
        Returns:
            np.ndarray: 约束向量
        """
        if not constraints:
            return np.zeros(target_dim)
        
        # 提取目标值和权重
        values = np.array([c.target_value for c in constraints])
        weights = np.array([c.weight for c in constraints])
        
        # 加权值
        weighted_values = values * weights
        
        # 扩展到目标维度
        if len(weighted_values) < target_dim:
            # 重复填充
            repeat_count = target_dim // len(weighted_values) + 1
            vector = np.tile(weighted_values, repeat_count)[:target_dim]
        else:
            # 截断
            vector = weighted_values[:target_dim]
        
        return vector
    
    def calculate_violation(
        self,
        response_vector: np.ndarray,
        constraints: List[StyleConstraint],
    ) -> float:
        """计算约束违反度
        
        Args:
            response_vector: 回复向量
            constraints: 约束列表
        
        Returns:
            float: 违反度 0-1（越低越好）
        """
        if not constraints or len(response_vector) == 0:
            return 0.0
        
        # 将约束转换为向量
        constraint_vector = self.to_vector(constraints, len(response_vector))
        
        # 计算余弦相似度
        dot_product = np.dot(response_vector, constraint_vector)
        norm_r = np.linalg.norm(response_vector)
        norm_c = np.linalg.norm(constraint_vector)
        
        if norm_r == 0 or norm_c == 0:
            return 1.0
        
        cosine_similarity = dot_product / (norm_r * norm_c)
        
        # 违反度 = 1 - 相似度
        violation = 1.0 - cosine_similarity
        
        return violation

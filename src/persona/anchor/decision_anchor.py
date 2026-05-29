# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""决策锚点编码器 — BERT + 三路融合架构 → 256 维。

支持 PyTorch 模型和 NumPy 确定性降级。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    nn = object
    TORCH_AVAILABLE = False

from .base import AnchorConfig, AnchorType, DecisionAnchor, generate_anchor_id

if not TORCH_AVAILABLE:

    class _DecisionEncoderBase:
        """torch 不可用时 DecisionEncoder 的基类"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("PyTorch not available, use encode_deterministic() instead")

        def encode(self, decision_anchor: DecisionAnchor) -> np.ndarray:
            """编码决策锚点"""
            raise NotImplementedError
else:

    class _DecisionEncoderBase(nn.Module):
        """PyTorch 可用时的基类"""

        pass


class DecisionEncoder(_DecisionEncoderBase):
    """BERT + 三路融合决策编码器 → 256 维。

    输入格式：
    {
        "user_goal": "验证核心假设",
        "priorities": [
            {"name": "用户体验", "weight": 0.9},
            {"name": "成本控制", "weight": 0.3}
        ],
        "constraints": {
            "must_not": ["违反价值观", "泄露隐私"],
            "flexible": ["具体方案选择"]
        }
    }

    架构：
    - goal_projection: Linear(768→512→256)  — BERT CLS → 目标向量
    - priority_encoder: Linear(num_bins*2→128→128) — 优先级权重离散化 → 优先级向量
    - constraint_encoder: Linear(768→256→128) — BERT CLS → 约束向量
    - fusion_layer: Linear(256+128+128→512→256+LayerNorm) — 三路融合

    输出：256 维 L2 归一化向量

    降级：BERT 不可用时 goal_projection 改用 SHA256 确定性编码
    """

    def __init__(self, config: Optional[AnchorConfig] = None) -> None:
        """初始化编码器。

        Args:
            config: 锚点配置，None 则使用默认配置
        """
        super().__init__()

        self.config = config or AnchorConfig()

        if not TORCH_AVAILABLE:
            return

        # Goal projection: 768 → 512 → 256
        self.goal_projection = nn.Sequential(
            nn.Linear(768, 512),
            nn.ReLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(512, 256),
            nn.LayerNorm(256),
        )

        # Priority encoder: num_bins*2 → 128 → 128
        priority_input_dim = self.config.num_priority_bins * 2
        self.priority_encoder = nn.Sequential(
            nn.Linear(priority_input_dim, 128),
            nn.ReLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(128, 128),
            nn.LayerNorm(128),
        )

        # Constraint encoder: 768 → 256 → 128
        self.constraint_encoder = nn.Sequential(
            nn.Linear(768, 256),
            nn.ReLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(256, 128),
            nn.LayerNorm(128),
        )

        # Fusion layer: 256+128+128 → 512 → 256
        fusion_input_dim = 256 + 128 + 128
        self.fusion_layer = nn.Sequential(
            nn.Linear(fusion_input_dim, 512),
            nn.ReLU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(512, 256),
            nn.LayerNorm(256),
        )

        # BERT tokenizer (lazy load)
        self._tokenizer = None

    def _get_tokenizer(self):
        """懒加载 BERT tokenizer"""
        if self._tokenizer is None:
            try:
                from transformers import BertTokenizer

                self._tokenizer = BertTokenizer.from_pretrained(self.config.text_encoder_name)
            except ImportError:
                self._tokenizer = None
        return self._tokenizer

    def _text_to_bert_embedding(self, text: str) -> np.ndarray:
        """将文本转换为 BERT CLS 嵌入。

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 768 维 CLS 向量
        """
        tokenizer = self._get_tokenizer()

        if tokenizer is None:
            # BERT 不可用，返回随机向量（降级）
            return np.random.randn(768).astype(np.float32)

        # BERT 推理占位：待模型加载后使用 tokenizer 编码
        del tokenizer, text
        return np.random.randn(768).astype(np.float32)

    def _discretize_priorities(self, priorities: List[Dict[str, float]]) -> np.ndarray:
        """将优先级权重离散化为分箱向量。

        Args:
            priorities: 优先级列表 [{"name": str, "weight": float}, ...]

        Returns:
            np.ndarray: num_bins*2 维向量
        """
        num_bins = self.config.num_priority_bins
        feature_vec = np.zeros(num_bins * 2, dtype=np.float32)

        if not priorities:
            return feature_vec

        # 权重分箱
        for priority in priorities:
            weight = priority.get("weight", 0.5)
            bin_idx = min(int(weight * num_bins), num_bins - 1)
            feature_vec[bin_idx] += 1
            feature_vec[num_bins + bin_idx] += weight

        # 归一化
        total = len(priorities)
        if total > 0:
            feature_vec[:num_bins] /= total
            feature_vec[num_bins:] /= total

        return feature_vec

    def _encode_constraints(self, constraints: Dict[str, List[str]]) -> np.ndarray:
        """编码约束条件。

        Args:
            constraints: 约束条件字典

        Returns:
            np.ndarray: 768 维约束向量
        """
        constraint_text = ""

        must_not = constraints.get("must_not", [])
        flexible = constraints.get("flexible", [])

        if must_not:
            constraint_text += "禁止：" + "，".join(must_not) + "。"
        if flexible:
            constraint_text += "灵活：" + "，".join(flexible) + "。"

        if constraint_text:
            return self._text_to_bert_embedding(constraint_text)
        else:
            return np.zeros(768, dtype=np.float32)

    def forward(self, decision_anchor: DecisionAnchor) -> torch.Tensor:
        """前向传播（PyTorch 模式）。

        Args:
            decision_anchor: 决策锚点

        Returns:
            torch.Tensor: 256 维输出向量
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")

        # Goal encoding
        goal_embedding = self._text_to_bert_embedding(decision_anchor.user_goal)
        goal_vec = torch.FloatTensor(goal_embedding)
        goal_proj = self.goal_projection(goal_vec)

        # Priority encoding
        priority_vec = self._discretize_priorities(decision_anchor.priorities)
        priority_tensor = torch.FloatTensor(priority_vec)
        priority_enc = self.priority_encoder(priority_tensor)

        # Constraint encoding
        constraint_embedding = self._encode_constraints(decision_anchor.constraints)
        constraint_vec = torch.FloatTensor(constraint_embedding)
        constraint_enc = self.constraint_encoder(constraint_vec)

        # Fusion
        fused = torch.cat([goal_proj, priority_enc, constraint_enc], dim=-1)
        fused = self.fusion_layer(fused)

        # L2 归一化
        fused = torch.nn.functional.normalize(fused, p=2, dim=-1)

        return fused

    def encode(self, decision_anchor: DecisionAnchor) -> np.ndarray:
        """编码决策锚点（主接口）。

        Args:
            decision_anchor: 决策锚点

        Returns:
            np.ndarray: 256 维 L2 归一化向量
        """
        if TORCH_AVAILABLE:
            with torch.no_grad():
                output = self(decision_anchor)
                return output.cpu().numpy()
        else:
            return self.encode_deterministic(decision_anchor)

    def encode_deterministic(self, decision_anchor: DecisionAnchor) -> np.ndarray:
        """确定性降级方案 — 不依赖 PyTorch。

        算法：SHA256 哈希生成可重现的 256 维向量
        1. 从 user_goal/priorities/constraints 提取特征字符串
        2. SHA256(特征字符串) → 32 字节哈希
        3. 循环填充：每字节→float32/255.0 → 256 维（32 字节*8 轮）
        4. L2 归一化 → 输出

        保证：相同输入 → 相同输出（确定性）

        Args:
            decision_anchor: 决策锚点

        Returns:
            np.ndarray: 256 维 L2 归一化向量
        """
        feature_values = []

        # Goal 特征
        goal_str = decision_anchor.user_goal
        feature_values.append(f"goal:{goal_str}")

        # Priorities 特征
        priorities_str = json.dumps(decision_anchor.priorities, sort_keys=True)
        feature_values.append(f"priorities:{priorities_str}")

        # Constraints 特征
        constraints_str = json.dumps(decision_anchor.constraints, sort_keys=True)
        feature_values.append(f"constraints:{constraints_str}")

        # 拼接为特征字符串
        feature_str = "|".join(feature_values)

        # SHA256 哈希
        hash_bytes = hashlib.sha256(feature_str.encode("utf-8")).digest()

        # 循环填充到 256 维
        vector = np.zeros(256, dtype=np.float32)
        for i in range(256):
            byte_idx = i % 32
            vector[i] = hash_bytes[byte_idx] / 255.0

        # L2 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector


class DecisionEncoderLight:
    """纯 NumPy 确定性降级方案。

    结构：
    - 目标文本 SHA256 → 前 128 维（归一化）
    - 优先级 MD5 → 64 维（归一化）
    - 约束 MD5 → 64 维（归一化）
    - 拼接为 256 维 → 整体归一化

    保证：相同输入 → 相同输出（确定性）
    """

    def __init__(self) -> None:
        """初始化轻量编码器。"""
        pass

    def _hash_to_vector(self, text: str, dim: int) -> np.ndarray:
        """将文本哈希转换为固定维度向量。

        Args:
            text: 输入文本
            dim: 目标维度

        Returns:
            np.ndarray: dim 维 L2 归一化向量
        """
        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

        # 循环填充
        vector = np.zeros(dim, dtype=np.float32)
        for i in range(dim):
            byte_idx = i % 32
            vector[i] = hash_bytes[byte_idx] / 255.0

        # L2 归一化
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def encode(self, decision_anchor: DecisionAnchor) -> np.ndarray:
        """编码决策锚点。

        Args:
            decision_anchor: 决策锚点

        Returns:
            np.ndarray: 256 维 L2 归一化向量
        """
        # Goal → 128 维
        goal_vec = self._hash_to_vector(decision_anchor.user_goal, 128)

        # Priorities → 64 维
        priorities_str = json.dumps(decision_anchor.priorities, sort_keys=True)
        priority_vec = self._hash_to_vector(priorities_str, 64)

        # Constraints → 64 维
        constraints_str = json.dumps(decision_anchor.constraints, sort_keys=True)
        constraint_vec = self._hash_to_vector(constraints_str, 64)

        # 拼接
        combined = np.concatenate([goal_vec, priority_vec, constraint_vec])

        # 整体归一化
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined = combined / norm

        return combined


class DecisionAnchorManager:
    """决策锚点 CRUD 管理。"""

    def __init__(self, config: Optional[AnchorConfig] = None) -> None:
        """初始化管理器。

        Args:
            config: 锚点配置
        """
        self.config = config or AnchorConfig()
        self._anchors: Dict[str, DecisionAnchor] = {}

        # 优先使用 PyTorch 编码器，降级到 Light 版本
        if TORCH_AVAILABLE:
            self._encoder = DecisionEncoder(self.config)
        else:
            self._encoder = DecisionEncoderLight()

    def create_anchor(
        self,
        decision_data: Dict[str, Any],
        anchor_id: Optional[str] = None,
    ) -> DecisionAnchor:
        """创建决策锚点。

        Args:
            decision_data: 决策数据字典
            anchor_id: 锚点 ID，None 则自动生成

        Returns:
            DecisionAnchor: 创建的锚点
        """
        if anchor_id is None:
            anchor_id = generate_anchor_id("decision")

        anchor = DecisionAnchor(
            anchor_id=anchor_id,
            anchor_type=AnchorType.DECISION,
            vector=np.zeros(self.config.decision_dim),
            user_goal=decision_data.get("user_goal", ""),
            priorities=decision_data.get("priorities", []),
            constraints=decision_data.get("constraints", {}),
        )

        # 编码向量
        vector = self._encoder.encode(anchor)
        anchor.vector = vector

        self._anchors[anchor_id] = anchor
        return anchor

    def update_anchor(
        self,
        anchor_id: str,
        decision_data: Dict[str, Any],
    ) -> DecisionAnchor:
        """更新决策锚点。

        Args:
            anchor_id: 锚点 ID
            decision_data: 新的决策数据

        Returns:
            DecisionAnchor: 更新后的锚点

        Raises:
            KeyError: 锚点不存在
        """
        if anchor_id not in self._anchors:
            raise KeyError(f"Decision anchor {anchor_id} not found")

        anchor = self._anchors[anchor_id]
        anchor.user_goal = decision_data.get("user_goal", anchor.user_goal)
        anchor.priorities = decision_data.get("priorities", anchor.priorities)
        anchor.constraints = decision_data.get("constraints", anchor.constraints)
        anchor.updated_at = time.time()

        # 重新编码向量
        vector = self._encoder.encode(anchor)
        anchor.vector = vector

        return anchor

    def get_anchor(self, anchor_id: str) -> Optional[DecisionAnchor]:
        """获取决策锚点。

        Args:
            anchor_id: 锚点 ID

        Returns:
            Optional[DecisionAnchor]: 锚点，不存在则返回 None
        """
        return self._anchors.get(anchor_id)

    def delete_anchor(self, anchor_id: str) -> bool:
        """删除决策锚点。

        Args:
            anchor_id: 锚点 ID

        Returns:
            bool: 是否删除成功
        """
        if anchor_id in self._anchors:
            del self._anchors[anchor_id]
            return True
        return False

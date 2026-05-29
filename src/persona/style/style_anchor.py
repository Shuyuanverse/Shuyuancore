# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""128 维风格锚点编码器，支持 PyTorch 模型和确定性降级。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    nn = object
    TORCH_AVAILABLE = False


@dataclass
class StyleAnchor:
    """风格锚点。
    
    Attributes:
        anchor_id: 锚点 ID
        vector: 128 维向量
        source_texts: 源文本列表
        metadata: 元数据
        created_at: 创建时间
        updated_at: 更新时间
    """
    anchor_id: str
    vector: np.ndarray
    source_texts: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


if not TORCH_AVAILABLE:
    class _StyleEncoderBase:
        """torch 不可用时 StyleAnchorEncoder 的基类"""
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
        
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("PyTorch not available, use encode_deterministic() instead")
        
        def encode_deterministic(self, style_features: Dict) -> np.ndarray:
            """始终可用的确定性编码"""
            raise NotImplementedError
else:
    class _StyleEncoderBase(nn.Module):  # type: ignore
        """PyTorch 可用时的基类"""
        pass


class StyleAnchorEncoder(_StyleEncoderBase):  # type: ignore
    """128 维风格锚点编码器。
    
    PyTorch 模式架构：
    - style_projection: Linear(256, 256) → ReLU → Dropout(0.1) → Linear(256, 128) → LayerNorm
    - core_feature_encoder: Linear(10, 32) → ReLU → Linear(32, 64)
    - fusion_layer: Linear(128+64, 128) → ReLU → Dropout(0.1) → LayerNorm
    
    输入：style_features 字典，包含：
    - 'style_vector': 60 维 StyleVector
    - 'style_profile': 7 维 StyleProfile 维度值
    - 'core_features': 10 维核心特征
    - 'text_features': StyleExtractionResult
    
    输出：128 维 L2 归一化向量
    """
    
    def __init__(self, input_dim: int = 256, hidden_dim: int = 256, output_dim: int = 128) -> None:
        """初始化编码器。
        
        Args:
            input_dim: 输入维度，默认 256
            hidden_dim: 隐藏层维度，默认 256
            output_dim: 输出维度，默认 128
        """
        super().__init__()
        
        if not TORCH_AVAILABLE:
            return
        
        self.style_projection = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
            nn.LayerNorm(output_dim),
        )
        
        self.core_feature_encoder = nn.Sequential(
            nn.Linear(10, 32),
            nn.ReLU(),
            nn.Linear(32, 64),
        )
        
        self.fusion_layer = nn.Sequential(
            nn.Linear(output_dim + 64, output_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.LayerNorm(output_dim),
        )
        
        self.output_dim = output_dim
    
    def forward(self, style_features: Dict) -> torch.Tensor:
        """前向传播（PyTorch 模式）。
        
        Args:
            style_features: 风格特征字典
            
        Returns:
            torch.Tensor: 128 维输出向量
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")
        
        style_vector = style_features.get("style_vector", np.zeros(60))
        profile_vector = style_features.get("profile_vector", np.zeros(7))
        core_features = style_features.get("core_features", np.zeros(10))
        
        style_input = np.concatenate([style_vector, profile_vector])
        style_input = torch.FloatTensor(style_input)
        
        core_vec = torch.FloatTensor(core_features)
        core_vec = self.core_feature_encoder(core_vec)
        
        style_vec = self.style_projection(style_input)
        
        fused = torch.cat([style_vec, core_vec], dim=-1)
        fused = self.fusion_layer(fused)
        
        fused = torch.nn.functional.normalize(fused, p=2, dim=-1)
        
        return fused
    
    def encode_deterministic(self, style_features: Dict) -> np.ndarray:
        """确定性降级方案 — 不依赖 PyTorch，始终可用。
        
        算法：SHA256 哈希生成可重现的 128 维向量
        1. 从 style_features 提取所有数值特征，拼接为特征字符串
        2. SHA256(特征字符串) → 32 字节哈希
        3. 循环填充：每字节→float32/255.0 → 128 维（32 字节*4 轮）
        4. L2 归一化 → 输出
        
        保证：相同输入 → 相同输出（确定性）
        
        Args:
            style_features: 风格特征字典
            
        Returns:
            np.ndarray: 128 维 L2 归一化向量
        """
        feature_values = []
        
        style_vector = style_features.get("style_vector", np.zeros(60))
        if isinstance(style_vector, np.ndarray):
            feature_values.extend(style_vector.tolist())
        elif hasattr(style_vector, "vector"):
            feature_values.extend(style_vector.vector.tolist())
        else:
            feature_values.extend([0.0] * 60)
        
        profile_vector = style_features.get("profile_vector", [])
        if isinstance(profile_vector, (list, np.ndarray)):
            feature_values.extend(profile_vector)
        else:
            feature_values.extend([0.5] * 7)
        
        core_features = style_features.get("core_features", np.zeros(10))
        if isinstance(core_features, np.ndarray):
            feature_values.extend(core_features.tolist())
        else:
            feature_values.extend([0.5] * 10)
        
        feature_str = ",".join(f"{v:.6f}" for v in feature_values)
        
        hash_bytes = hashlib.sha256(feature_str.encode("utf-8")).digest()
        
        vector = np.zeros(128, dtype=np.float32)
        for i in range(128):
            byte_idx = i % 32
            vector[i] = hash_bytes[byte_idx] / 255.0
        
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector
    
    def freeze(self) -> None:
        """冻结编码器参数（requires_grad=False）。"""
        if TORCH_AVAILABLE:
            for param in self.parameters():
                param.requires_grad = False
    
    def unfreeze(self) -> None:
        """解冻编码器参数。"""
        if TORCH_AVAILABLE:
            for param in self.parameters():
                param.requires_grad = True


class StyleAnchorManager:
    """风格锚点 CRUD 管理。"""
    
    def __init__(self) -> None:
        """初始化管理器。"""
        self._anchors: Dict[str, StyleAnchor] = {}
        self._encoder = StyleAnchorEncoder()
    
    def create_anchor(
        self,
        style_features: Dict,
        anchor_id: str,
        source_texts: List[str],
        metadata: Dict[str, Any],
    ) -> StyleAnchor:
        """创建风格锚点。
        
        Args:
            style_features: 风格特征
            anchor_id: 锚点 ID
            source_texts: 源文本列表
            metadata: 元数据
            
        Returns:
            StyleAnchor: 创建的锚点
        """
        from datetime import datetime
        
        if TORCH_AVAILABLE and hasattr(style_features.get("style_vector"), "vector"):
            vector_tensor = self._encoder(style_features)
            vector = vector_tensor.detach().cpu().numpy()
        else:
            vector = self._encoder.encode_deterministic(style_features)
        
        anchor = StyleAnchor(
            anchor_id=anchor_id,
            vector=vector,
            source_texts=source_texts,
            metadata=metadata,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        
        self._anchors[anchor_id] = anchor
        return anchor
    
    def update_anchor(self, anchor_id: str, style_features: Dict) -> StyleAnchor:
        """更新风格锚点。
        
        Args:
            anchor_id: 锚点 ID
            style_features: 新的风格特征
            
        Returns:
            StyleAnchor: 更新后的锚点
            
        Raises:
            KeyError: 锚点不存在
        """
        from datetime import datetime
        
        if anchor_id not in self._anchors:
            raise KeyError(f"Anchor {anchor_id} not found")
        
        if TORCH_AVAILABLE:
            vector_tensor = self._encoder(style_features)
            vector = vector_tensor.detach().cpu().numpy()
        else:
            vector = self._encoder.encode_deterministic(style_features)
        
        anchor = self._anchors[anchor_id]
        anchor.vector = vector
        anchor.updated_at = datetime.utcnow().isoformat()
        
        return anchor
    
    def get_anchor(self, anchor_id: str) -> Optional[StyleAnchor]:
        """获取风格锚点。
        
        Args:
            anchor_id: 锚点 ID
            
        Returns:
            Optional[StyleAnchor]: 锚点，不存在则返回 None
        """
        return self._anchors.get(anchor_id)
    
    def delete_anchor(self, anchor_id: str) -> bool:
        """删除风格锚点。
        
        Args:
            anchor_id: 锚点 ID
            
        Returns:
            bool: 是否删除成功
        """
        if anchor_id in self._anchors:
            del self._anchors[anchor_id]
            return True
        return False
    
    def batch_encode(self, style_features_list: List[Dict]) -> List[np.ndarray]:
        """批量编码风格特征。
        
        Args:
            style_features_list: 风格特征列表
            
        Returns:
            List[np.ndarray]: 128 维向量列表
        """
        vectors = []
        for features in style_features_list:
            if TORCH_AVAILABLE:
                vector_tensor = self._encoder(features)
                vector = vector_tensor.detach().cpu().numpy()
            else:
                vector = self._encoder.encode_deterministic(features)
            vectors.append(vector)
        return vectors


def extract_style_from_text(texts: List[str]) -> Dict:
    """便捷函数：从文本提取 10 维核心特征。
    
    10 维核心特征：
    1. avg_sentence_length  2. emoji_density  3. avg_paragraph_length
    4. question_ratio       5. exclamation_ratio  6. emoji_variety
    7. hashtag_density      8. at_mention_density  9. exclamation_density
    10. punctuation_variety
    
    Args:
        texts: 文本列表
        
    Returns:
        Dict: 10 维核心特征字典
    """
    import re
    
    if not texts:
        return {
            "avg_sentence_length": 0.0,
            "emoji_density": 0.0,
            "avg_paragraph_length": 0.0,
            "question_ratio": 0.0,
            "exclamation_ratio": 0.0,
            "emoji_variety": 0.0,
            "hashtag_density": 0.0,
            "at_mention_density": 0.0,
            "exclamation_density": 0.0,
            "punctuation_variety": 0.0,
        }
    
    total_chars = 0
    total_sentences = 0
    total_paragraphs = 0
    emoji_counts: Dict[str, int] = Counter()
    question_count = 0
    exclamation_count = 0
    hashtag_count = 0
    at_mention_count = 0
    punct_set: set = set()
    
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    
    for text in texts:
        total_chars += len(text)
        
        sentences = [s for s in re.split(r"[.!??.!?]", text) if s.strip()]
        total_sentences += len(sentences)
        
        paragraphs = [p for p in text.split("\n") if p.strip()]
        total_paragraphs += len(paragraphs)
        
        emojis = emoji_pattern.findall(text)
        for emoji in emojis:
            emoji_counts[emoji] += 1
        
        question_count += text.count("?") + text.count("?")
        exclamation_count += text.count("!") + text.count("！")
        hashtag_count += text.count("#")
        at_mention_count += text.count("@")
        
        for char in text:
            if char in "，。！？、；：""''（）【】《》—……·～":
                punct_set.add(char)
    
    total_sentences = max(total_sentences, 1)
    total_paragraphs = max(total_paragraphs, 1)
    
    return {
        "avg_sentence_length": total_chars / total_sentences / 50.0,
        "emoji_density": sum(emoji_counts.values()) / max(total_chars, 1),
        "avg_paragraph_length": total_chars / total_paragraphs / 200.0,
        "question_ratio": question_count / total_sentences,
        "exclamation_ratio": exclamation_count / total_sentences,
        "emoji_variety": len(emoji_counts) / 50.0,
        "hashtag_density": hashtag_count / max(total_paragraphs, 1),
        "at_mention_density": at_mention_count / max(total_sentences, 1),
        "exclamation_density": exclamation_count / max(total_chars, 1),
        "punctuation_variety": len(punct_set) / 20.0,
    }


from collections import Counter

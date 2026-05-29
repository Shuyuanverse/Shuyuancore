# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""LLM 语义翻译器 — 将锚点向量 + 分身数据→25 维价值观画像。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np

from .value_dimensions import ValueDimensionsRegistry


class SemanticTranslator:
    """LLM 语义翻译器。
    
    调用 LLM 将锚点向量和分身数据转换为 25 维价值观评分的 JSON 格式。
    """
    
    def __init__(self) -> None:
        """初始化翻译器。"""
        self.registry = ValueDimensionsRegistry()
        self._llm_client = None
    
    def translate(
        self,
        style_vector: np.ndarray,
        decision_vector: np.ndarray,
        persona_data: Dict[str, Any],
        language_samples: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """翻译为 25 维价值观画像。
        
        Args:
            style_vector: 128 维风格向量
            decision_vector: 256 维决策向量
            persona_data: 分身数据（包含用户设定的性格描述等）
            language_samples: 语言样本列表
            
        Returns:
            Dict[str, float]: 25 维价值观评分 {维度名：评分}
        """
        # 构建 LLM prompt
        prompt = self._build_prompt(style_vector, decision_vector, persona_data, language_samples)
        
        # 调用 LLM
        llm_response = self._call_llm(prompt)
        
        # 解析 JSON 响应
        values_profile = self._parse_response(llm_response)
        
        # 验证和修正
        values_profile = self._validate_and_fix(values_profile)
        
        return values_profile
    
    def _build_prompt(
        self,
        style_vector: np.ndarray,
        decision_vector: np.ndarray,
        persona_data: Dict[str, Any],
        language_samples: Optional[List[str]],
    ) -> str:
        """构建 LLM prompt。
        
        Args:
            style_vector: 风格向量
            decision_vector: 决策向量
            persona_data: 分身数据
            language_samples: 语言样本
            
        Returns:
            str: LLM prompt
        """
        # 提取向量特征
        style_summary = self._summarize_vector(style_vector, "style")
        decision_summary = self._summarize_vector(decision_vector, "decision")
        
        # 构建 prompt
        prompt = f"""你是一个人格分析专家。请根据以下信息分析用户的 25 维价值观画像。

## 风格向量特征
{style_summary}

## 决策向量特征
{decision_summary}

## 用户设定的人格描述
{persona_data.get("description", "无")}

## 语言样本
{language_samples[:5] if language_samples else "无"}

## 任务
请输出 25 个价值观维度的评分（0-1），格式为 JSON：
{{
    "warmth": 0.6,
    "boundary_awareness": 0.5,
    ...
}}

25 个维度：{', '.join(d.name for d in self.registry.get_all_dimensions())}

注意：
1. 评分必须基于向量特征和语言样本，不能随意猜测
2. 输出必须是纯 JSON，不要包含其他文字
3. 每个维度评分在 0-1 之间
"""
        
        return prompt
    
    def _summarize_vector(self, vector: np.ndarray, vector_type: str) -> str:
        """总结向量特征。
        
        Args:
            vector: 向量
            vector_type: 向量类型
            
        Returns:
            str: 特征总结
        """
        # 简化处理：返回统计信息
        return f"{vector_type}向量 (维度{len(vector)}): 均值={np.mean(vector):.3f}, 标准差={np.std(vector):.3f}, 最大值={np.max(vector):.3f}, 最小值={np.min(vector):.3f}"
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM。
        
        Args:
            prompt: 输入 prompt
            
        Returns:
            str: LLM 响应
            
        Raises:
            RuntimeError: LLM 调用失败
        """
        # 简化实现：返回占位响应
        # 实际实现需要调用 DashScope/DeepSeek 等 LLM API
        
        default_values = self.registry.get_default_values()
        return json.dumps(default_values, indent=2, ensure_ascii=False)
    
    def _parse_response(self, response: str) -> Dict[str, float]:
        """解析 LLM 响应。
        
        Args:
            response: LLM 响应文本
            
        Returns:
            Dict[str, float]: 价值观评分字典
            
        Raises:
            ValueError: JSON 解析失败
        """
        try:
            # 尝试提取 JSON 部分
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                values = json.loads(json_str)
            else:
                values = json.loads(response)
            
            return values
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response: {e}")
    
    def _validate_and_fix(self, values: Dict[str, float]) -> Dict[str, float]:
        """验证和修正价值观评分。
        
        Args:
            values: 原始评分
            
        Returns:
            Dict[str, float]: 修正后的评分
        """
        fixed_values = {}
        default_values = self.registry.get_default_values()
        
        for dim in self.registry.get_all_dimensions():
            value = values.get(dim.name, default_values[dim.name])
            
            # 范围检查
            value = max(dim.min_value, min(dim.max_value, value))
            
            fixed_values[dim.name] = value
        
        return fixed_values

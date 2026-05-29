# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""约束引导解码器 — Prompt 工程实现。

ConstrainedDecoder 将 ConstraintVector 转换为风格指南文本注入 Prompt

decode(prompt, constraints, context) → DecodingResult
1. 将 ConstraintVector.dimensions 转换为风格指南文本
   - lexical 类型："使用以下口头禅（适量）：{phrases}"
   - syntactic 类型："句子偏短/偏长"
   - tonal 类型："语调积极正面/客观冷静"
2. 构建带风格指南的完整 Prompt
3. 调用 LLM 生成
4. 返回 DecodingResult

adjust_constraint_strength(current_satisfaction, target=0.85) → float
# 动态调整约束强度
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DecodingResult:
    """解码结果
    
    Attributes:
        generated_text: 生成的文本
        style_guide: 风格指南
        constraints_applied: 应用的约束列表
        satisfaction_score: 满意度分数
        metadata: 元数据
    """
    
    generated_text: str
    style_guide: str = ""
    constraints_applied: List[str] = field(default_factory=list)
    satisfaction_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "generated_text": self.generated_text,
            "style_guide": self.style_guide,
            "constraints_applied": self.constraints_applied,
            "satisfaction_score": self.satisfaction_score,
            "metadata": self.metadata,
        }


class ConstrainedDecoder:
    """约束引导解码器 — Prompt 工程实现
    
    将 ConstraintVector 转换为风格指南文本注入 Prompt
    
    decode(prompt, constraints, context) → DecodingResult
    1. 将 ConstraintVector.dimensions 转换为风格指南文本
    2. 构建带风格指南的完整 Prompt
    3. 调用 LLM 生成
    4. 返回 DecodingResult
    
    adjust_constraint_strength(current_satisfaction, target=0.85) → float
    # 动态调整约束强度
    """
    
    def __init__(self):
        """初始化约束引导解码器"""
        logger.info("[constrained_decoder] 初始化完成")
    
    def decode(
        self,
        prompt: str,
        constraints: Any,  # ConstraintVector
        context: Optional[Dict[str, Any]] = None,
    ) -> DecodingResult:
        """解码
        
        Args:
            prompt: 基础提示词
            constraints: 约束向量
            context: 上下文信息
        
        Returns:
            DecodingResult: 解码结果
        """
        # Step 1: 将约束转换为风格指南
        style_guide = self._convert_to_style_guide(constraints)
        
        # Step 2: 构建完整 Prompt
        full_prompt = self._build_full_prompt(prompt, style_guide)
        
        # Step 3: 调用 LLM 生成（简化实现）
        generated_text = self._call_llm(full_prompt, context)
        
        # Step 4: 计算满意度分数（简化）
        satisfaction_score = self._calculate_satisfaction(generated_text, constraints)
        
        # 提取应用的约束
        constraints_applied = self._extract_applied_constraints(constraints)
        
        result = DecodingResult(
            generated_text=generated_text,
            style_guide=style_guide,
            constraints_applied=constraints_applied,
            satisfaction_score=satisfaction_score,
            metadata={
                "prompt_length": len(prompt),
                "style_guide_length": len(style_guide),
                "context": context,
            },
        )
        
        logger.info(
            "[constrained_decoder] 解码完成：satisfaction=%.2f, constraints=%d",
            satisfaction_score,
            len(constraints_applied),
        )
        
        return result
    
    def adjust_constraint_strength(
        self,
        current_satisfaction: float,
        target: float = 0.85,
    ) -> float:
        """动态调整约束强度
        
        Args:
            current_satisfaction: 当前满意度
            target: 目标满意度
        
        Returns:
            float: 调整后的约束强度
        """
        # 计算差距
        gap = target - current_satisfaction
        
        # 调整策略
        if gap > 0.2:
            # 满意度偏低，降低约束强度
            adjustment = -0.1
        elif gap < -0.2:
            # 满意度偏高，可以增加约束强度
            adjustment = 0.05
        else:
            # 满意度接近目标，微调
            adjustment = gap * 0.1
        
        # 限制调整幅度
        adjustment = max(-0.2, min(0.2, adjustment))
        
        logger.debug(
            "[constrained_decoder] 调整约束强度：satisfaction=%.2f, adjustment=%.2f",
            current_satisfaction,
            adjustment,
        )
        
        return adjustment
    
    def _convert_to_style_guide(self, constraints: Any) -> str:
        """将约束转换为风格指南
        
        Args:
            constraints: 约束向量
        
        Returns:
            str: 风格指南文本
        """
        if not constraints or not hasattr(constraints, 'dimensions'):
            return ""
        
        guide_lines = ["【风格指南】"]
        
        for dim in constraints.dimensions:
            if not dim.enabled:
                continue
            
            dim_type = dim.constraint_type
            target_value = dim.target_value
            
            # 根据类型生成指南
            if dim_type == "lexical":
                if "catchphrase" in dim.name:
                    guide_lines.append(f"- 使用口头禅（适量）：{target_value}")
                elif "vocabulary" in dim.name:
                    guide_lines.append(f"- 词汇风格：{target_value}")
            
            elif dim_type == "syntactic":
                if "sentence_length" in dim.name:
                    if target_value < 20:
                        guide_lines.append("- 句子偏短，简洁有力")
                    elif target_value > 50:
                        guide_lines.append("- 句子偏长，详细阐述")
                    else:
                        guide_lines.append("- 句子长度适中")
            
            elif dim_type == "tonal":
                if "tone" in dim.name:
                    if target_value > 0.7:
                        guide_lines.append("- 语调积极正面")
                    elif target_value < 0.3:
                        guide_lines.append("- 语调客观冷静")
                    else:
                        guide_lines.append("- 语调中性平和")
        
        guide_lines.append("")
        
        return "\n".join(guide_lines)
    
    def _build_full_prompt(self, prompt: str, style_guide: str) -> str:
        """构建完整 Prompt
        
        Args:
            prompt: 基础提示词
            style_guide: 风格指南
        
        Returns:
            str: 完整提示词
        """
        if not style_guide:
            return prompt
        
        return f"{style_guide}\n{prompt}"
    
    def _call_llm(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """调用 LLM 生成
        
        Args:
            prompt: 提示词
            context: 上下文
        
        Returns:
            str: 生成的文本
        """
        # 简化实现：返回占位文本
        # TODO: 实现真实的 LLM 调用
        return f"【生成回复】{prompt[:50]}..."
    
    def _calculate_satisfaction(
        self,
        generated_text: str,
        constraints: Any,
    ) -> float:
        """计算满意度分数
        
        Args:
            generated_text: 生成的文本
            constraints: 约束向量
        
        Returns:
            float: 满意度分数 0-1
        """
        # 简化实现：返回固定值
        return 0.85
    
    def _extract_applied_constraints(self, constraints: Any) -> List[str]:
        """提取应用的约束
        
        Args:
            constraints: 约束向量
        
        Returns:
            List[str]: 约束名称列表
        """
        if not constraints or not hasattr(constraints, 'dimensions'):
            return []
        
        return [dim.name for dim in constraints.dimensions if dim.enabled]

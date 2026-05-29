# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""25 维价值观定义。

定义人格的 25 个价值观维度及其默认值、范围约束。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ValueRange(Enum):
    """价值观取值范围"""
    ZERO_TO_ONE = "zero_to_one"  # 0-1
    NEG_ONE_TO_ONE = "neg_one_to_one"  # -1 到 1
    PERCENT = "percent"  # 0-100


@dataclass
class ValueDimension:
    """价值观维度定义。
    
    Attributes:
        name: 维度名称
        description: 描述
        default_value: 默认值
        min_value: 最小值
        max_value: 最大值
        range_type: 范围类型
    """
    name: str
    description: str
    default_value: float = 0.5
    min_value: float = 0.0
    max_value: float = 1.0
    range_type: ValueRange = ValueRange.ZERO_TO_ONE


class ValueDimensionsRegistry:
    """25 维价值观注册表。
    
    提供维度定义、默认值、范围约束。
    """
    
    # 25 维价值观定义
    DIMENSIONS = [
        ValueDimension(
            name="warmth",
            description="温暖度 - 对他人的关怀和友善程度",
            default_value=0.6,
        ),
        ValueDimension(
            name="boundary_awareness",
            description="边界意识 - 对个人空间和他人边界的敏感度",
            default_value=0.5,
        ),
        ValueDimension(
            name="humor_preference",
            description="幽默偏好 - 对幽默和轻松氛围的喜好程度",
            default_value=0.5,
        ),
        ValueDimension(
            name="aggression",
            description="攻击性 - 对抗和冲突倾向",
            default_value=0.2,
        ),
        ValueDimension(
            name="patience",
            description="耐心 - 容忍延迟和挫折的能力",
            default_value=0.6,
        ),
        ValueDimension(
            name="curiosity",
            description="好奇心 - 探索新事物的欲望",
            default_value=0.7,
        ),
        ValueDimension(
            name="expressiveness",
            description="表现力 - 情感和想法的外显程度",
            default_value=0.5,
        ),
        ValueDimension(
            name="empathy",
            description="同理心 - 理解和分享他人情感的能力",
            default_value=0.7,
        ),
        ValueDimension(
            name="stubbornness",
            description="固执 - 坚持己见的程度",
            default_value=0.3,
        ),
        ValueDimension(
            name="risk_taking",
            description="冒险倾向 - 承担风险的意愿",
            default_value=0.4,
        ),
        ValueDimension(
            name="social_need",
            description="社交需求 - 对社交互动的渴望",
            default_value=0.5,
        ),
        ValueDimension(
            name="solitude_need",
            description="独处需求 - 对独处时间的需求",
            default_value=0.5,
        ),
        ValueDimension(
            name="emotional_volatility",
            description="情绪波动 - 情绪变化的幅度和频率",
            default_value=0.3,
        ),
        ValueDimension(
            name="rationality",
            description="理性 - 逻辑思考胜过情感的程度",
            default_value=0.6,
        ),
        ValueDimension(
            name="sensitivity",
            description="敏感度 - 对外界刺激的敏感程度",
            default_value=0.5,
        ),
        ValueDimension(
            name="self_disclosure",
            description="自我表露 - 分享个人信息的开放程度",
            default_value=0.4,
        ),
        ValueDimension(
            name="control_need",
            description="控制欲 - 对环境和结果的掌控需求",
            default_value=0.4,
        ),
        ValueDimension(
            name="trust_level",
            description="信任度 - 对他人的信任倾向",
            default_value=0.6,
        ),
        ValueDimension(
            name="loyalty",
            description="忠诚度 - 对人/组织的忠诚程度",
            default_value=0.7,
        ),
        ValueDimension(
            name="independent_thinking",
            description="独立思考 - 不盲从的批判性思维倾向",
            default_value=0.7,
        ),
        ValueDimension(
            name="obedience",
            description="顺从性 - 遵循权威和规则的程度",
            default_value=0.4,
        ),
        ValueDimension(
            name="defensiveness",
            description="防御性 - 面对批评时的防御倾向",
            default_value=0.3,
        ),
        ValueDimension(
            name="self_deprecation",
            description="自嘲 - 拿自己开玩笑的倾向",
            default_value=0.4,
        ),
        ValueDimension(
            name="silence_preference",
            description="沉默偏好 - 对安静和不说话的偏好",
            default_value=0.3,
        ),
        ValueDimension(
            name="rhythm_sense",
            description="节奏感 - 对对话和交流节奏的敏感度",
            default_value=0.5,
        ),
    ]
    
    def __init__(self) -> None:
        """初始化注册表。"""
        self._custom_dimensions: Dict[str, ValueDimension] = {}
    
    def get_dimension(self, name: str) -> Optional[ValueDimension]:
        """获取维度定义。
        
        Args:
            name: 维度名称
            
        Returns:
            Optional[ValueDimension]: 维度定义，不存在则返回 None
        """
        for dim in self.DIMENSIONS:
            if dim.name == name:
                return dim
        
        return self._custom_dimensions.get(name)
    
    def get_all_dimensions(self) -> List[ValueDimension]:
        """获取所有维度定义。
        
        Returns:
            List[ValueDimension]: 维度定义列表
        """
        return self.DIMENSIONS + list(self._custom_dimensions.values())
    
    def get_default_values(self) -> Dict[str, float]:
        """获取所有维度的默认值。
        
        Returns:
            Dict[str, float]: {维度名：默认值} 字典
        """
        return {dim.name: dim.default_value for dim in self.DIMENSIONS}
    
    def validate_value(self, dimension_name: str, value: float) -> Tuple[bool, str]:
        """验证价值观取值是否合法。
        
        Args:
            dimension_name: 维度名称
            value: 取值
            
        Returns:
            Tuple[bool, str]: (是否合法，错误消息)
        """
        dim = self.get_dimension(dimension_name)
        
        if dim is None:
            return False, f"Unknown dimension: {dimension_name}"
        
        if value < dim.min_value or value > dim.max_value:
            return False, f"Value {value} out of range [{dim.min_value}, {dim.max_value}]"
        
        return True, ""
    
    def add_custom_dimension(
        self,
        name: str,
        description: str,
        default_value: float = 0.5,
        min_value: float = 0.0,
        max_value: float = 1.0,
    ) -> bool:
        """添加自定义维度。
        
        Args:
            name: 维度名称
            description: 描述
            default_value: 默认值
            min_value: 最小值
            max_value: 最大值
            
        Returns:
            bool: 是否添加成功
        """
        if name in [d.name for d in self.DIMENSIONS]:
            return False
        
        if name in self._custom_dimensions:
            return False
        
        self._custom_dimensions[name] = ValueDimension(
            name=name,
            description=description,
            default_value=default_value,
            min_value=min_value,
            max_value=max_value,
        )
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "dimensions": [
                {
                    "name": dim.name,
                    "description": dim.description,
                    "default": dim.default_value,
                    "range": [dim.min_value, dim.max_value],
                }
                for dim in self.DIMENSIONS + list(self._custom_dimensions.values())
            ],
            "total_count": len(self.DIMENSIONS) + len(self._custom_dimensions),
        }

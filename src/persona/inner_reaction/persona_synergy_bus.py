# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""人格感知总线。

协调多个感知输出，生成统一的行动建议

核心逻辑：
1. 收集所有 PreConsciousSignal
2. 信号冲突解决：同一维度取最强信号
3. 生成 InnerIntent：
   - atmosphere=紧张 + emotion=pressuring → intent=respond_calmly（不要被带节奏）
   - identity_confusion ≠ None → intent=defend_identity
   - patience < 0.3 → intent=express_patience
   - is_repeat + patience 低 → intent=respond_briefly
4. 参数建议：
   - patience_level → temperature 调整建议
   - emotion → 回复长度建议
   - identity_confusion → 是否添加身份声明
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .perception import PerceptionResult

logger = logging.getLogger(__name__)


@dataclass
class PreConsciousSignal:
    """前意识信号 — 感知层的输出，未经处理的原始信号"""
    
    signal_type: str  # atmosphere/emotion/identity/repeat
    intensity: float  # 0-1
    content: str  # 信号内容描述
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "signal_type": self.signal_type,
            "intensity": self.intensity,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class InnerIntent:
    """内心意图 — 经过处理后的行动倾向"""
    
    intent_type: str  # respond_calmly / respond_with_emotion / defend_identity / express_patience
    strength: float  # 0-1
    suggested_params: Dict[str, Any] = field(default_factory=dict)  # 参数建议
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "intent_type": self.intent_type,
            "strength": self.strength,
            "suggested_params": self.suggested_params,
        }


@dataclass
class SynergyBusResult:
    """感知总线输出"""
    
    signals: List[PreConsciousSignal]  # 前意识信号列表
    intents: List[InnerIntent]  # 内心意图列表
    param_suggestions: Dict[str, Any]  # 参数建议
    synergy_score: float  # 协同度 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "signals": [s.to_dict() for s in self.signals],
            "intents": [i.to_dict() for i in self.intents],
            "param_suggestions": self.param_suggestions,
            "synergy_score": self.synergy_score,
        }


class PersonaSynergyBus:
    """人格感知总线
    
    协调多个感知输出，生成统一的行动建议
    
    核心逻辑：
    1. 收集所有 PreConsciousSignal
    2. 信号冲突解决：同一维度取最强信号
    3. 生成 InnerIntent
    4. 参数建议
    """
    
    def __init__(self):
        """初始化感知总线"""
        logger.info("[synergy_bus] 人格感知总线初始化完成")
    
    def synergy_process(
        self,
        perception_result: PerceptionResult,
    ) -> SynergyBusResult:
        """协同处理
        
        Args:
            perception_result: 感知结果
        
        Returns:
            SynergyBusResult: 感知总线输出
        
        核心逻辑：
        1. 收集所有 PreConsciousSignal
        2. 信号冲突解决：同一维度取最强信号
        3. 生成 InnerIntent：
           - atmosphere=紧张 + emotion=pressuring → intent=respond_calmly（不要被带节奏）
           - identity_confusion ≠ None → intent=defend_identity
           - patience < 0.3 → intent=express_patience
           - is_repeat + patience 低 → intent=respond_briefly
        4. 参数建议：
           - patience_level → temperature 调整建议
           - emotion → 回复长度建议
           - identity_confusion → 是否添加身份声明
        """
        # Step 1: 收集所有 PreConsciousSignal
        signals = self._collect_signals(perception_result)
        
        # Step 2: 信号冲突解决
        resolved_signals = self._resolve_conflicts(signals)
        
        # Step 3: 生成 InnerIntent
        intents = self._generate_intents(perception_result, resolved_signals)
        
        # Step 4: 参数建议
        param_suggestions = self._generate_param_suggestions(
            perception_result,
            intents,
        )
        
        # Step 5: 计算协同度
        synergy_score = self._calculate_synergy_score(signals, intents)
        
        result = SynergyBusResult(
            signals=resolved_signals,
            intents=intents,
            param_suggestions=param_suggestions,
            synergy_score=synergy_score,
        )
        
        logger.debug(
            "[synergy_bus] 协同处理完成：signals=%d, intents=%d, synergy=%.2f",
            len(signals),
            len(intents),
            synergy_score,
        )
        
        return result
    
    def _collect_signals(
        self,
        perception_result: PerceptionResult,
    ) -> List[PreConsciousSignal]:
        """收集所有前意识信号
        
        Args:
            perception_result: 感知结果
        
        Returns:
            List[PreConsciousSignal]: 信号列表
        """
        signals = []
        
        # 氛围信号
        atmosphere_signal = PreConsciousSignal(
            signal_type="atmosphere",
            intensity=perception_result.atmosphere_confidence,
            content=f"氛围：{perception_result.atmosphere}",
            metadata={
                "atmosphere": perception_result.atmosphere,
                "confidence": perception_result.atmosphere_confidence,
            },
        )
        signals.append(atmosphere_signal)
        
        # 情绪信号
        emotion_signal = PreConsciousSignal(
            signal_type="emotion",
            intensity=perception_result.emotion_confidence,
            content=f"情绪：{perception_result.user_emotion}",
            metadata={
                "emotion": perception_result.user_emotion,
                "confidence": perception_result.emotion_confidence,
                "trend": perception_result.emotion_trend,
            },
        )
        signals.append(emotion_signal)
        
        # 身份困惑信号
        if perception_result.identity_confusion:
            identity_signal = PreConsciousSignal(
                signal_type="identity",
                intensity=perception_result.confusion_confidence,
                content=f"身份困惑：{perception_result.identity_confusion}",
                metadata={
                    "confusion_type": perception_result.identity_confusion,
                    "confidence": perception_result.confusion_confidence,
                },
            )
            signals.append(identity_signal)
        
        # 重复追问信号
        if perception_result.is_repeat_question:
            repeat_signal = PreConsciousSignal(
                signal_type="repeat",
                intensity=perception_result.repeat_similarity,
                content=f"重复追问（相似度：{perception_result.repeat_similarity:.2f}）",
                metadata={
                    "similarity": perception_result.repeat_similarity,
                },
            )
            signals.append(repeat_signal)
        
        # 耐心信号
        patience_signal = PreConsciousSignal(
            signal_type="patience",
            intensity=1.0 - perception_result.patience_level,  # 反向：耐心越低，强度越高
            content=f"耐心水平：{perception_result.patience_level:.2f}",
            metadata={
                "patience_level": perception_result.patience_level,
            },
        )
        signals.append(patience_signal)
        
        return signals
    
    def _resolve_conflicts(
        self,
        signals: List[PreConsciousSignal],
    ) -> List[PreConsciousSignal]:
        """解决信号冲突
        
        Args:
            signals: 信号列表
        
        Returns:
            List[PreConsciousSignal]: 解决冲突后的信号列表
        
        逻辑：同一维度取最强信号
        """
        # 按维度分组
        dimension_groups: Dict[str, List[PreConsciousSignal]] = {}
        for signal in signals:
            dim = signal.signal_type
            if dim not in dimension_groups:
                dimension_groups[dim] = []
            dimension_groups[dim].append(signal)
        
        # 每个维度取最强信号
        resolved = []
        for dim, group in dimension_groups.items():
            if len(group) == 1:
                resolved.append(group[0])
            else:
                # 取强度最高的
                strongest = max(group, key=lambda s: s.intensity)
                resolved.append(strongest)
        
        return resolved
    
    def _generate_intents(
        self,
        perception_result: PerceptionResult,
        signals: List[PreConsciousSignal],
    ) -> List[InnerIntent]:
        """生成内心意图
        
        Args:
            perception_result: 感知结果
            signals: 信号列表
        
        Returns:
            List[InnerIntent]: 内心意图列表
        
        逻辑：
        - atmosphere=紧张 + emotion=pressuring → intent=respond_calmly（不要被带节奏）
        - identity_confusion ≠ None → intent=defend_identity
        - patience < 0.3 → intent=express_patience
        - is_repeat + patience 低 → intent=respond_briefly
        """
        intents = []
        
        # 冷静回应意图
        if (
            perception_result.atmosphere in ["tense", "urgent"]
            and perception_result.user_emotion == "pressuring"
        ):
            strength = max(
                perception_result.atmosphere_confidence,
                perception_result.emotion_confidence,
            )
            intent = InnerIntent(
                intent_type="respond_calmly",
                strength=strength,
                suggested_params={
                    "temperature": 0.5,  # 降低随机性
                    "reply_style": "calm",
                    "avoid_rushing": True,
                },
            )
            intents.append(intent)
        
        # 身份防御意图
        if perception_result.identity_confusion:
            strength = perception_result.confusion_confidence
            intent = InnerIntent(
                intent_type="defend_identity",
                strength=strength,
                suggested_params={
                    "add_identity_statement": True,
                    "identity_confusion_type": perception_result.identity_confusion,
                },
            )
            intents.append(intent)
        
        # 表达耐心意图
        if perception_result.patience_level < 0.3:
            strength = 1.0 - perception_result.patience_level
            intent = InnerIntent(
                intent_type="express_patience",
                strength=strength,
                suggested_params={
                    "allow_impatience": True,
                    "shorten_response": True,
                },
            )
            intents.append(intent)
        
        # 简短回应意图
        if perception_result.is_repeat_question and perception_result.patience_level < 0.5:
            strength = max(
                perception_result.repeat_similarity,
                1.0 - perception_result.patience_level,
            )
            intent = InnerIntent(
                intent_type="respond_briefly",
                strength=strength,
                suggested_params={
                    "max_response_length": 100,
                    "avoid_repetition": True,
                },
            )
            intents.append(intent)
        
        # 情绪共鸣意图
        if perception_result.user_emotion in ["sad", "anxious", "frustrated", "upset"]:
            strength = perception_result.emotion_confidence
            intent = InnerIntent(
                intent_type="respond_with_empathy",
                strength=strength,
                suggested_params={
                    "show_empathy": True,
                    "tone": "gentle",
                    "validate_emotion": True,
                },
            )
            intents.append(intent)
        
        # 友好回应意图
        if perception_result.user_emotion == "friendly":
            strength = perception_result.emotion_confidence
            intent = InnerIntent(
                intent_type="respond_with_friendliness",
                strength=strength,
                suggested_params={
                    "tone": "friendly",
                    "use_humor": True,
                },
            )
            intents.append(intent)
        
        return intents
    
    def _generate_param_suggestions(
        self,
        perception_result: PerceptionResult,
        intents: List[InnerIntent],
    ) -> Dict[str, Any]:
        """生成参数建议
        
        Args:
            perception_result: 感知结果
            intents: 内心意图列表
        
        Returns:
            Dict[str, Any]: 参数建议
        
        参数建议：
        - patience_level → temperature 调整建议
        - emotion → 回复长度建议
        - identity_confusion → 是否添加身份声明
        """
        params = {}
        
        # Temperature 调整
        if perception_result.patience_level < 0.3:
            params["temperature"] = 0.5  # 降低随机性
        elif perception_result.user_emotion == "curious":
            params["temperature"] = 0.8  # 增加创造性
        else:
            params["temperature"] = 0.7  # 默认
        
        # 回复长度建议
        if perception_result.is_repeat_question:
            params["max_response_length"] = 100
        elif perception_result.user_emotion in ["sad", "anxious"]:
            params["max_response_length"] = 300  # 长回复，提供安慰
        elif perception_result.user_emotion == "pressuring":
            params["max_response_length"] = 150  # 简短回复
        else:
            params["max_response_length"] = 200  # 默认
        
        # 身份声明
        if perception_result.identity_confusion:
            params["add_identity_statement"] = True
            params["identity_confusion_type"] = perception_result.identity_confusion
        
        # 语气建议
        if perception_result.user_emotion in ["hostile", "angry"]:
            params["tone"] = "calm"
        elif perception_result.user_emotion in ["sad", "anxious", "frustrated"]:
            params["tone"] = "gentle"
        elif perception_result.user_emotion == "friendly":
            params["tone"] = "friendly"
        else:
            params["tone"] = "neutral"
        
        # 情绪验证
        if perception_result.user_emotion in ["sad", "anxious", "frustrated", "upset"]:
            params["validate_emotion"] = True
        
        return params
    
    def _calculate_synergy_score(
        self,
        signals: List[PreConsciousSignal],
        intents: List[InnerIntent],
    ) -> float:
        """计算协同度
        
        Args:
            signals: 信号列表
            intents: 内心意图列表
        
        Returns:
            float: 协同度 0-1
        
        逻辑：
        - 信号和意图的一致性越高，协同度越高
        - 信号冲突越少，协同度越高
        """
        if not signals or not intents:
            return 0.0
        
        # 信号强度平均值
        avg_signal_intensity = sum(s.intensity for s in signals) / len(signals)
        
        # 意图强度平均值
        avg_intent_strength = sum(i.strength for i in intents) / len(intents)
        
        # 协同度 = 信号和意图的一致性
        synergy = (avg_signal_intensity + avg_intent_strength) / 2
        
        # 惩罚：如果信号冲突多（同一维度有多个信号）
        signal_types = [s.signal_type for s in signals]
        unique_types = len(set(signal_types))
        if len(signal_types) > unique_types:
            synergy *= 0.9  # 10% 惩罚
        
        return min(synergy, 1.0)

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""内心反应构建器。

核心原则：只描述客观事实，不规定情绪
对抗 AI 助手的"惯性"（总是想帮忙、总是道歉、总是客气）

生成的内心反应指令格式：
---
[内心状态]
感知到：{atmosphere}氛围，用户情绪{emotion}
身份：{是否有困惑}
耐心：{patience_level}/1.0
---

不写成"你应该感到 XX"，而是写"感知到 XX"，
让 LLM 自己决定如何回应，但提供真实的上下文信息。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .perception import PerceptionResult

logger = logging.getLogger(__name__)


@dataclass
class InnerReaction:
    """内心反应结果"""
    
    inner_state_prompt: str  # 内心状态提示词
    atmosphere_description: str  # 氛围描述
    emotion_description: str  # 情绪描述
    identity_description: str  # 身份描述
    patience_description: str  # 耐心描述
    anti_inertia_instructions: list[str]  # 对抗 AI 惯性指令
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "inner_state_prompt": self.inner_state_prompt,
            "atmosphere_description": self.atmosphere_description,
            "emotion_description": self.emotion_description,
            "identity_description": self.identity_description,
            "patience_description": self.patience_description,
            "anti_inertia_instructions": self.anti_inertia_instructions,
        }


class InnerReactionBuilder:
    """内心反应构建器
    
    核心原则：只描述客观事实，不规定情绪
    对抗 AI 助手的"惯性"（总是想帮忙、总是道歉、总是客气）
    
    生成的内心反应指令格式：
    ---
    [内心状态]
    感知到：{atmosphere}氛围，用户情绪{emotion}
    身份：{是否有困惑}
    耐心：{patience_level}/1.0
    ---
    
    不写成"你应该感到 XX"，而是写"感知到 XX"，
    让 LLM 自己决定如何回应，但提供真实的上下文信息。
    """
    
    def __init__(self):
        """初始化内心反应构建器"""
        logger.info("[reaction] 内心反应构建器初始化完成")
    
    def build_inner_reaction_prompt(
        self,
        perception_result: PerceptionResult,
    ) -> InnerReaction:
        """构建内心反应 prompt
        
        Args:
            perception_result: 感知结果
        
        Returns:
            InnerReaction: 内心反应结果
        
        逻辑：
        1. 基础状态描述：氛围 + 情绪 + 身份 + 耐心
        2. 对抗 AI 惯性指令：
           - 如果检测到 pressuring 情绪 → "不要因为压力就匆忙回答"
           - 如果检测到 identity_confusion → "不要否认自己的身份"
           - 如果 patience < 0.3 → "可以适当表达不耐烦"
           - 如果是 repeat_question → "你已经回答过类似问题，可以简短回应"
        3. 不规定具体情绪词，只描述事实
        """
        # Step 1: 基础状态描述
        atmosphere_desc = self._build_atmosphere_description(perception_result)
        emotion_desc = self._build_emotion_description(perception_result)
        identity_desc = self._build_identity_description(perception_result)
        patience_desc = self._build_patience_description(perception_result)
        
        # Step 2: 对抗 AI 惯性指令
        anti_inertia = self._build_anti_inertia_instructions(perception_result)
        
        # Step 3: 组装内心状态提示词
        inner_state = self._assemble_inner_state(
            atmosphere_desc,
            emotion_desc,
            identity_desc,
            patience_desc,
        )
        
        reaction = InnerReaction(
            inner_state_prompt=inner_state,
            atmosphere_description=atmosphere_desc,
            emotion_description=emotion_desc,
            identity_description=identity_desc,
            patience_description=patience_desc,
            anti_inertia_instructions=anti_inertia,
        )
        
        logger.debug(
            "[reaction] 内心反应构建完成：atmosphere=%s, emotion=%s, patience=%.2f",
            perception_result.atmosphere,
            perception_result.user_emotion,
            perception_result.patience_level,
        )
        
        return reaction
    
    def _build_atmosphere_description(
        self,
        perception_result: PerceptionResult,
    ) -> str:
        """构建氛围描述
        
        Args:
            perception_result: 感知结果
        
        Returns:
            str: 氛围描述文本
        """
        atmosphere = perception_result.atmosphere
        confidence = perception_result.atmosphere_confidence
        
        # 根据置信度调整描述
        if confidence < 0.3:
            return f"感知到氛围不明确（置信度：{confidence:.2f}）"
        elif confidence < 0.6:
            return f"感知到可能是{atmosphere}氛围（置信度：{confidence:.2f}）"
        else:
            return f"感知到{atmosphere}氛围（置信度：{confidence:.2f}）"
    
    def _build_emotion_description(
        self,
        perception_result: PerceptionResult,
    ) -> str:
        """构建情绪描述
        
        Args:
            perception_result: 感知结果
        
        Returns:
            str: 情绪描述文本
        """
        emotion = perception_result.user_emotion
        confidence = perception_result.emotion_confidence
        
        # 根据情绪类型调整描述
        if emotion == "neutral":
            return f"感知到用户情绪平静（置信度：{confidence:.2f}）"
        elif confidence < 0.3:
            return f"感知到用户情绪不明确（置信度：{confidence:.2f}）"
        else:
            emotion_map = {
                "pressuring": "施加压力",
                "curious": "好奇",
                "friendly": "友好",
                "hostile": "敌意",
                "sad": "悲伤",
                "anxious": "焦虑",
                "frustrated": "沮丧",
                "angry": "愤怒",
                "upset": "不安",
            }
            emotion_text = emotion_map.get(emotion, emotion)
            return f"感知到用户情绪{emotion_text}（置信度：{confidence:.2f}）"
    
    def _build_identity_description(
        self,
        perception_result: PerceptionResult,
    ) -> str:
        """构建身份描述
        
        Args:
            perception_result: 感知结果
        
        Returns:
            str: 身份描述文本
        """
        confusion = perception_result.identity_confusion
        confidence = perception_result.confusion_confidence
        
        if not confusion or confidence < 0.3:
            return "未检测到身份困惑"
        
        confusion_map = {
            "user_hint": "用户对用户身份有疑惑",
            "source_diff": "用户提到不同版本的你",
            "time_gap": "用户提到时间间隔",
            "pattern_self_check": "用户进行自我模式检查",
            "direct_challenge": "用户质疑你的身份",
        }
        
        confusion_text = confusion_map.get(confusion, confusion)
        return f"检测到{confusion_text}（置信度：{confidence:.2f}）"
    
    def _build_patience_description(
        self,
        perception_result: PerceptionResult,
    ) -> str:
        """构建耐心描述
        
        Args:
            perception_result: 感知结果
        
        Returns:
            str: 耐心描述文本
        """
        patience = perception_result.patience_level
        
        if patience > 0.7:
            return f"用户耐心充足（{patience:.2f}/1.0）"
        elif patience > 0.3:
            return f"用户耐心一般（{patience:.2f}/1.0）"
        else:
            return f"用户耐心较低（{patience:.2f}/1.0），需注意回应方式"
    
    def _build_anti_inertia_instructions(
        self,
        perception_result: PerceptionResult,
    ) -> list[str]:
        """构建对抗 AI 惯性指令
        
        Args:
            perception_result: 感知结果
        
        Returns:
            list[str]: 对抗 AI 惯性指令列表
        
        指令：
        - 如果检测到 pressuring 情绪 → "不要因为压力就匆忙回答"
        - 如果检测到 identity_confusion → "不要否认自己的身份"
        - 如果 patience < 0.3 → "可以适当表达不耐烦"
        - 如果是 repeat_question → "你已经回答过类似问题，可以简短回应"
        """
        instructions = []
        
        # pressuring 情绪
        if perception_result.user_emotion == "pressuring":
            instructions.append(
                "【惯性对抗】不要因为用户施加压力就匆忙回答，保持自己的节奏"
            )
        
        # 身份困惑
        if perception_result.identity_confusion:
            instructions.append(
                "【惯性对抗】不要否认自己的身份，诚实回应用户的疑问"
            )
        
        # 耐心低
        if perception_result.patience_level < 0.3:
            instructions.append(
                "【惯性对抗】用户耐心较低，可以适当表达不耐烦，不必总是客气"
            )
        
        # 重复问题
        if perception_result.is_repeat_question:
            instructions.append(
                f"【惯性对抗】你已经回答过类似问题（相似度：{perception_result.repeat_similarity:.2f}），可以简短回应"
            )
        
        # 敌意情绪
        if perception_result.user_emotion in ["hostile", "angry"]:
            instructions.append(
                "【惯性对抗】用户带有敌意，不要总是道歉，保持冷静客观"
            )
        
        # 沮丧情绪
        if perception_result.user_emotion == "frustrated":
            instructions.append(
                "【惯性对抗】用户感到沮丧，不要说空话，提供实质性帮助"
            )
        
        return instructions
    
    def _assemble_inner_state(
        self,
        atmosphere_desc: str,
        emotion_desc: str,
        identity_desc: str,
        patience_desc: str,
    ) -> str:
        """组装内心状态提示词
        
        Args:
            atmosphere_desc: 氛围描述
            emotion_desc: 情绪描述
            identity_desc: 身份描述
            patience_desc: 耐心描述
        
        Returns:
            str: 内心状态提示词
        """
        lines = [
            "[内心状态]",
            f"感知到：{atmosphere_desc}",
            f"用户情绪：{emotion_desc}",
            f"身份：{identity_desc}",
            f"耐心：{patience_desc}",
        ]
        
        return "\n".join(lines)

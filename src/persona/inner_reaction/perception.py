# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""纯规则感知引擎 — 零 LLM 调用。

感知 4 大类信号：
1. 氛围感知 — 4 类：轻松/紧张/紧急/日常
2. 用户情绪 — 10 类：neutral/pressuring/curious/friendly/hostile/sad/anxious/frustrated/angry/upset
3. 身份困惑 — 5 类：user_hint/source_diff/time_gap/pattern_self_check/direct_challenge
4. 重复追问检测 — Jaccard 相似度
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 氛围关键词库
ATMOSPHERE_KEYWORDS: Dict[str, List[str]] = {
    "relaxed": ["哈哈", "嘿嘿", "好玩", "有趣", "开心", "棒", "不错", "轻松", "随便", "聊聊"],
    "tense": ["紧张", "急", "快", "赶紧", "马上", "立刻", " ASAP ", "快点", "赶快"],
    "urgent": ["紧急", "严重", "出问题了", "崩了", "挂了", "报警", "危机", "故障", "错误"],
    "daily": ["你好", "早上好", "晚上好", "在吗", "hi", "hello", "早", "好", "嗨"],
}

# 用户情绪关键词库
USER_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "neutral": [],
    "pressuring": ["必须", "一定", "非要", "赶紧", "赶快", "快一点", "立刻", "马上", "务必"],
    "curious": ["为什么", "怎么回事", "好奇", "什么意思", "怎么理解", "如何", "原理", "啥"],
    "friendly": ["谢谢", "辛苦", "厉害", "不错", "帮忙", "感谢", "多谢", "棒", "好"],
    "hostile": ["无聊", "废话", "啰嗦", "烦", "讨厌", "垃圾", "没用", "差劲"],
    "sad": ["难过", "伤心", "失望", "遗憾", "可惜", "心痛", "悲伤", "失落"],
    "anxious": ["担心", "焦虑", "不安", "害怕", "紧张", "忐忑", "慌", "怕"],
    "frustrated": ["烦死了", "受不了", "崩溃", "不行了", "太难了", "头疼", "无语"],
    "angry": ["生气", "愤怒", "气死", "恼火", "火大", "暴怒", "气愤", "怒"],
    "upset": ["委屈", "不公平", "凭什么", "不爽", "不高兴", "郁闷", "难受"],
}

# 身份困惑模式
IDENTITY_CONFUSION_PATTERNS: Dict[str, List[str]] = {
    "user_hint": ["你不是", "你不该", "你应该是", "你怎么会", "你不对", "你错了"],
    "source_diff": ["另一个你", "之前的你", "上次你说", "以前你", "之前的版本"],
    "time_gap": ["好久不见", "上次聊天", "你还记得", "之前我们", "上次我们"],
    "pattern_self_check": [],
    "direct_challenge": ["你是谁", "你是 AI 吗", "你是机器人吗", "你到底是什么", "你是什么"],
}

# 重复追问检测阈值
REPEAT_SIMILARITY_THRESHOLD = 0.6
PATIENCE_DECAY_PER_REPEAT = 0.15
PATIENCE_DECAY_PER_NEGATIVE = 0.1
WOLF_THRESHOLD = 3  # 狼来了阈值


@dataclass
class PerceptionResult:
    """感知结果"""

    atmosphere: str = "daily"  # 氛围类型
    atmosphere_confidence: float = 0.0  # 氛围置信度
    user_emotion: str = "neutral"  # 用户情绪
    emotion_confidence: float = 0.0  # 情绪置信度
    identity_confusion: Optional[str] = None  # 身份困惑类型
    confusion_confidence: float = 0.0  # 困惑置信度
    is_repeat_question: bool = False  # 是否重复追问
    repeat_similarity: float = 0.0  # Jaccard 相似度
    patience_level: float = 1.0  # 耐心值（0-1，越低越不耐烦）
    emotion_trend: str = "stable"  # 情绪趋势：improving/declining/stable
    wolf_penalty: float = 0.0  # 狼来了惩罚值
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "atmosphere": self.atmosphere,
            "atmosphere_confidence": self.atmosphere_confidence,
            "user_emotion": self.user_emotion,
            "emotion_confidence": self.emotion_confidence,
            "identity_confusion": self.identity_confusion,
            "confusion_confidence": self.confusion_confidence,
            "is_repeat_question": self.is_repeat_question,
            "repeat_similarity": self.repeat_similarity,
            "patience_level": self.patience_level,
            "emotion_trend": self.emotion_trend,
            "wolf_penalty": self.wolf_penalty,
            "metadata": self.metadata,
        }


class PerceptionEngine:
    """纯规则感知引擎 — 零 LLM 调用

    感知 4 大类信号：
    1. 氛围感知：关键词匹配 → 取最高匹配类别
    2. 用户情绪检测：关键词匹配 → 取最高匹配类别
    3. 身份困惑检测：模式匹配 → 返回困惑类型
    4. 重复追问检测：Jaccard 相似度（当前消息 vs 最近 3 条历史消息）

    属性：
        _wolf_counter: 狼来了计数器（检测用户频繁表达紧急但实际不紧急）
    """

    def __init__(self):
        """初始化感知引擎"""
        self._wolf_counter: Dict[str, int] = {}  # persona_id -> count
        logger.info("[perception] 感知引擎初始化完成")

    def perceive(
        self,
        user_message: str,
        history: List[str],
        persona_id: str,
    ) -> PerceptionResult:
        """主入口：纯规则感知

        Args:
            user_message: 用户消息
            history: 历史消息列表（最近 5-10 轮）
            persona_id: 人格 ID

        Returns:
            PerceptionResult: 感知结果

        算法流程：
        1. 氛围检测：关键词匹配 → 取最高匹配类别
        2. 用户情绪检测：关键词匹配 → 取最高匹配类别
        3. 身份困惑检测：模式匹配 → 返回困惑类型
        4. 重复追问检测：Jaccard 相似度（当前消息 vs 最近 3 条历史消息）
           Jaccard = |A∩B| / |A∪B|，超过 0.6 视为重复
        5. 耐心计算：基于最近 5 轮是否出现重复追问 + 负面情绪
           patience = max(0, 1.0 - repeat_count*0.15 - negative_emotion_count*0.1)
        6. 情绪趋势预测：最近 5 轮情绪序列
           - 连续 3 轮负面 → "declining"
           - 连续 3 轮正面 → "improving"
           - 其他 → "stable"
        7. 狼来了上下文修正：如果用户频繁表达紧急但实际不紧急，降低 atmosphere_confidence
        """
        # Step 1: 氛围检测
        atmosphere, atmosphere_conf = self._detect_atmosphere(user_message)

        # Step 2: 用户情绪检测
        emotion, emotion_conf = self._detect_emotion(user_message)

        # Step 3: 身份困惑检测
        confusion, confusion_conf = self._detect_identity_confusion(user_message)

        # Step 4: 重复追问检测
        is_repeat, repeat_sim = self._detect_repeat(user_message, history)

        # Step 5: 耐心计算
        patience = self._calculate_patience(user_message, history)

        # Step 6: 情绪趋势预测
        emotion_trend = self._predict_emotion_trend(history)

        # Step 7: 狼来了修正
        wolf_penalty = self._apply_boy_who_cried_wolf(
            atmosphere,
            atmosphere_conf,
            user_message,
            persona_id,
        )

        # 应用狼来了惩罚
        if wolf_penalty > 0:
            atmosphere_conf = max(0.0, atmosphere_conf - wolf_penalty)

        result = PerceptionResult(
            atmosphere=atmosphere,
            atmosphere_confidence=atmosphere_conf,
            user_emotion=emotion,
            emotion_confidence=emotion_conf,
            identity_confusion=confusion,
            confusion_confidence=confusion_conf,
            is_repeat_question=is_repeat,
            repeat_similarity=repeat_sim,
            patience_level=patience,
            emotion_trend=emotion_trend,
            wolf_penalty=wolf_penalty,
            metadata={
                "message_length": len(user_message),
                "history_length": len(history),
            },
        )

        logger.debug(
            "[perception] 感知完成：atmosphere=%s (%.2f), emotion=%s (%.2f), "
            "confusion=%s, repeat=%s, patience=%.2f, trend=%s",
            atmosphere,
            atmosphere_conf,
            emotion,
            emotion_conf,
            confusion,
            is_repeat,
            patience,
            emotion_trend,
        )

        return result

    def _detect_atmosphere(self, message: str) -> Tuple[str, float]:
        """检测氛围

        Args:
            message: 用户消息

        Returns:
            (atmosphere_type, confidence): 氛围类型和置信度
        """
        best_atmosphere = "daily"
        best_score = 0.0

        for atmosphere, keywords in ATMOSPHERE_KEYWORDS.items():
            if not keywords:
                continue

            # 计算匹配比例
            match_count = sum(1 for kw in keywords if kw in message)
            score = match_count / len(keywords)

            if score > best_score:
                best_score = score
                best_atmosphere = atmosphere

        # 归一化置信度到 0-1
        confidence = min(best_score * 2, 1.0)
        return best_atmosphere, confidence

    def _detect_emotion(self, message: str) -> Tuple[str, float]:
        """检测用户情绪

        Args:
            message: 用户消息

        Returns:
            (emotion_type, confidence): 情绪类型和置信度
        """
        best_emotion = "neutral"
        best_score = 0.0

        for emotion, keywords in USER_EMOTION_KEYWORDS.items():
            if not keywords:
                continue

            # 计算匹配比例
            match_count = sum(1 for kw in keywords if kw in message)
            score = match_count / len(keywords)

            if score > best_score:
                best_score = score
                best_emotion = emotion

        # 归一化置信度到 0-1
        confidence = min(best_score * 2, 1.0)
        return best_emotion, confidence

    def _detect_identity_confusion(self, message: str) -> Tuple[Optional[str], float]:
        """检测身份困惑

        Args:
            message: 用户消息

        Returns:
            (confusion_type, confidence): 困惑类型和置信度，无困惑则返回 (None, 0.0)
        """
        best_confusion: Optional[str] = None
        best_score = 0.0

        for confusion_type, patterns in IDENTITY_CONFUSION_PATTERNS.items():
            if not patterns:
                continue

            # 计算匹配比例
            match_count = sum(1 for pattern in patterns if pattern in message)
            score = match_count / len(patterns)

            if score > best_score:
                best_score = score
                best_confusion = confusion_type

        # 归一化置信度到 0-1
        confidence = min(best_score * 2, 1.0)

        # 置信度过低则视为无困惑
        if confidence < 0.1:
            return None, 0.0

        return best_confusion, confidence

    def _detect_repeat(self, message: str, history: List[str]) -> Tuple[bool, float]:
        """检测重复追问

        Args:
            message: 用户消息
            history: 历史消息列表

        Returns:
            (is_repeat, jaccard_similarity): 是否重复和 Jaccard 相似度

        算法：
        Jaccard = |A∩B| / |A∪B|
        其中 A 和 B 分别是两条消息的字符集合
        """
        if not history:
            return False, 0.0

        # 只检查最近 3 条消息
        recent_history = history[-3:]

        max_similarity = 0.0
        for prev_message in recent_history:
            # 计算 Jaccard 相似度
            set_a = set(message)
            set_b = set(prev_message)

            intersection = len(set_a & set_b)
            union = len(set_a | set_b)

            if union == 0:
                similarity = 0.0
            else:
                similarity = intersection / union

            max_similarity = max(max_similarity, similarity)

        is_repeat = max_similarity > REPEAT_SIMILARITY_THRESHOLD
        return is_repeat, max_similarity

    def _calculate_patience(
        self,
        current_message: str,
        history: List[str],
    ) -> float:
        """计算耐心值

        Args:
            current_message: 当前消息
            history: 历史消息列表

        Returns:
            float: 耐心值（0-1）

        算法：
        patience = max(0, 1.0 - repeat_count*0.15 - negative_emotion_count*0.1)
        """
        patience = 1.0

        # 检查最近 5 轮
        recent_history = history[-5:]

        repeat_count = 0
        negative_emotion_count = 0

        for prev_message in recent_history:
            # 检测重复
            is_repeat, _ = self._detect_repeat(prev_message, history)
            if is_repeat:
                repeat_count += 1

            # 检测负面情绪
            emotion, _ = self._detect_emotion(prev_message)
            if emotion in ["hostile", "angry", "frustrated", "upset"]:
                negative_emotion_count += 1

        # 计算耐心值
        patience -= repeat_count * PATIENCE_DECAY_PER_REPEAT
        patience -= negative_emotion_count * PATIENCE_DECAY_PER_NEGATIVE

        return max(patience, 0.0)

    def _predict_emotion_trend(self, history: List[str]) -> str:
        """预测情绪趋势

        Args:
            history: 历史消息列表

        Returns:
            str: 情绪趋势（improving/declining/stable）

        算法：
        - 连续 3 轮负面 → "declining"
        - 连续 3 轮正面 → "improving"
        - 其他 → "stable"
        """
        if len(history) < 3:
            return "stable"

        # 检查最近 5 轮
        recent_history = history[-5:]

        negative_emotions = ["hostile", "angry", "frustrated", "upset", "sad", "anxious"]
        positive_emotions = ["friendly", "curious"]

        negative_count = 0
        positive_count = 0

        for message in recent_history:
            emotion, _ = self._detect_emotion(message)
            if emotion in negative_emotions:
                negative_count += 1
            elif emotion in positive_emotions:
                positive_count += 1

        # 连续 3 轮负面
        if negative_count >= 3:
            return "declining"

        # 连续 3 轮正面
        if positive_count >= 3:
            return "improving"

        return "stable"

    def _apply_boy_who_cried_wolf(
        self,
        atmosphere: str,
        confidence: float,
        message: str,
        persona_id: str,
    ) -> float:
        """应用狼来了修正

        Args:
            atmosphere: 检测到的氛围
            confidence: 置信度
            message: 用户消息
            persona_id: 人格 ID

        Returns:
            float: 惩罚值（0.0-0.5）

        算法：
        如果用户频繁表达紧急（urgent/tense）但实际不紧急，降低置信度
        检测关键词：紧急、急、快、立刻、马上
        如果连续 3 次表达紧急但实际不紧急，第 4 次开始惩罚
        """
        urgent_keywords = ["紧急", "急", "快", "立刻", "马上", "赶紧", "赶快"]

        # 检测是否表达紧急
        is_expressing_urgent = any(kw in message for kw in urgent_keywords)

        if not is_expressing_urgent:
            # 重置计数器
            self._wolf_counter[persona_id] = 0
            return 0.0

        # 更新计数器
        count = self._wolf_counter.get(persona_id, 0) + 1
        self._wolf_counter[persona_id] = count

        # 前 3 次不惩罚
        if count <= WOLF_THRESHOLD:
            return 0.0

        # 第 4 次开始惩罚，每次增加 0.1，最高 0.5
        penalty = min(0.1 * (count - WOLF_THRESHOLD), 0.5)

        logger.info(
            "[perception] 狼来了检测：persona=%s, count=%d, penalty=%.2f",
            persona_id,
            count,
            penalty,
        )

        return penalty

    def reset_wolf_counter(self, persona_id: str) -> None:
        """重置狼来了计数器

        Args:
            persona_id: 人格 ID
        """
        self._wolf_counter[persona_id] = 0
        logger.info("[perception] 重置狼来了计数器：persona=%s", persona_id)

    def get_wolf_count(self, persona_id: str) -> int:
        """获取狼来了计数器值

        Args:
            persona_id: 人格 ID

        Returns:
            int: 计数器值
        """
        return self._wolf_counter.get(persona_id, 0)

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

REPEAT_SIMILARITY_THRESHOLD = 0.7
PATIENCE_DECAY_PER_REPEAT = 0.15
PATIENCE_DECAY_PER_TURN = 0.02

ATMOSPHERE_KEYWORDS: dict[str, list[str]] = {
    "relaxed": ["哈哈", "随便", "聊聊", "闲", "放松", "轻松"],
    "serious": ["必须", "严格", "重要", "紧急", "正式", "务必"],
    "pressing": ["立刻", "马上", "快点", "来不及", "尽快", "赶紧"],
    "playful": ["嘻嘻", "好玩", "有趣", "开玩笑", "萌萌", "调皮"],
}

EMOTION_KEYWORDS: dict[str, list[str]] = {
    "positive": ["开心", "赞", "棒", "谢谢", "太好了", "厉害"],
    "neutral": ["嗯", "好的", "明白", "知道", "看看", "考虑"],
    "curious": ["为什么", "怎么回事", "怎么理解", "什么意思", "如何", "原理"],
    "pressing": ["快点", "立刻", "马上", "来不及", "着急", "赶时间"],
    "negative_low": ["唉", "不太", "一般", "烦", "算了", "随便吧"],
    "negative_high": ["生气", "差", "烂", "失望", "愤怒", "投诉"],
}


@dataclass
class PerceptionResult:
    conversation_turn: int = 0
    repeat_count: int = 0
    conversation_duration_minutes: float = 0.0
    atmosphere: str = "relaxed"
    atmosphere_confidence: float = 0.0
    user_emotion_hint: str = "neutral"
    user_emotion_confidence: float = 0.0
    patience_level: float = 1.0
    identity_confusion: Optional[dict] = None
    emotion_trend: str = "stable"
    perception_summary: str = ""


def _detect_repeats(user_message: str, conversation_history: list[dict]) -> int:
    repeat_count = 0
    for prev_msg in conversation_history[-3:]:
        if prev_msg.get("role") == "user":
            sim = SequenceMatcher(None, user_message, prev_msg.get("content", "")).ratio()
            if sim > REPEAT_SIMILARITY_THRESHOLD:
                repeat_count += 1
    return repeat_count


def _detect_atmosphere(user_message: str) -> tuple[str, float]:
    best_atmosphere = "relaxed"
    best_score = 0.0
    for atmosphere, keywords in ATMOSPHERE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in user_message) / max(len(keywords), 1)
        if score > best_score:
            best_score = score
            best_atmosphere = atmosphere
    return best_atmosphere, min(best_score * 2, 1.0)


def _detect_emotion(user_message: str) -> tuple[str, float]:
    best_emotion = "neutral"
    best_score = 0.0
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in user_message) / max(len(keywords), 1)
        if score > best_score:
            best_score = score
            best_emotion = emotion
    return best_emotion, min(best_score * 2, 1.0)


def _compute_patience(repeat_count: int, conversation_turn: int) -> float:
    patience = 1.0
    patience -= repeat_count * PATIENCE_DECAY_PER_REPEAT
    patience -= conversation_turn * PATIENCE_DECAY_PER_TURN
    return max(patience, 0.1)


def _detect_emotion_trend(conversation_history: list[dict]) -> str:
    if len(conversation_history) < 4:
        return "stable"
    recent_emotions = []
    for msg in conversation_history[-6:]:
        if msg.get("role") == "user":
            emo, _ = _detect_emotion(msg.get("content", ""))
            recent_emotions.append(emo)
    negative_count = sum(1 for e in recent_emotions if e in ("negative_low", "negative_high"))
    positive_count = sum(1 for e in recent_emotions if e == "positive")
    if negative_count >= 3:
        return "escalating"
    if positive_count >= 3:
        return "de_escalating"
    return "stable"


def _build_summary(perception: PerceptionResult) -> str:
    parts = [
        f"对话轮次：{perception.conversation_turn}",
        f"氛围：{perception.atmosphere}",
        f"用户情绪：{perception.user_emotion_hint}",
        f"耐心水平：{perception.patience_level:.1f}",
        f"重复次数：{perception.repeat_count}",
        f"情绪趋势：{perception.emotion_trend}",
    ]
    return " | ".join(parts)


def perceive(
    user_message: str,
    conversation_history: list[dict],
    persona_id: str,
    style_profile: dict = None,
) -> PerceptionResult:
    conversation_turn = len(conversation_history)
    repeat_count = _detect_repeats(user_message, conversation_history)
    atmosphere, atmosphere_conf = _detect_atmosphere(user_message)
    emotion, emotion_conf = _detect_emotion(user_message)
    patience = _compute_patience(repeat_count, conversation_turn)
    emotion_trend = _detect_emotion_trend(conversation_history)

    result = PerceptionResult(
        conversation_turn=conversation_turn,
        repeat_count=repeat_count,
        atmosphere=atmosphere,
        atmosphere_confidence=atmosphere_conf,
        user_emotion_hint=emotion,
        user_emotion_confidence=emotion_conf,
        patience_level=patience,
        emotion_trend=emotion_trend,
    )
    result.perception_summary = _build_summary(result)
    return result

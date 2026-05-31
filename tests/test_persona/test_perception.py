from __future__ import annotations

import pytest

from src.persona.perception import (
    _compute_patience,
    _detect_atmosphere,
    _detect_emotion,
    _detect_emotion_trend,
    _detect_repeats,
    perceive,
)


class TestDetectRepeats:
    def test_no_repeat_returns_zero(self) -> None:
        history = [
            {"role": "user", "content": "今天天气怎么样"},
            {"role": "assistant", "content": "天气很好"},
        ]
        count = _detect_repeats("明天的天气呢", history)
        assert count == 0

    def test_identical_message_detected(self) -> None:
        history = [
            {"role": "user", "content": "帮我查一下资料"},
        ]
        count = _detect_repeats("帮我查一下资料", history)
        assert count == 1

    def test_high_similarity_detected(self) -> None:
        history = [
            {"role": "user", "content": "请帮我查一下最近的新闻"},
        ]
        count = _detect_repeats("请帮我查一下最近的新闻数据", history)
        assert count == 1

    def test_repeat_ignores_assistant_messages(self) -> None:
        history = [
            {"role": "assistant", "content": "你好，请问有什么可以帮您"},
            {"role": "assistant", "content": "你好，请问有什么可以帮您"},
        ]
        count = _detect_repeats("你好，请问有什么可以帮您", history)
        assert count == 0


class TestDetectAtmosphere:
    def test_relaxed_atmosphere(self) -> None:
        atm, conf = _detect_atmosphere("哈哈，随便聊聊")
        assert atm == "relaxed"
        assert conf > 0

    def test_serious_atmosphere(self) -> None:
        atm, conf = _detect_atmosphere("这个事情必须严格处理，非常重要")
        assert atm == "serious"
        assert conf > 0

    def test_pressing_atmosphere(self) -> None:
        atm, conf = _detect_atmosphere("快点，来不及了，立刻处理")
        assert atm == "pressing"
        assert conf > 0

    def test_playful_atmosphere(self) -> None:
        atm, conf = _detect_atmosphere("嘻嘻，这个好玩又有趣")
        assert atm == "playful"
        assert conf > 0

    def test_no_keyword_defaults_to_relaxed(self) -> None:
        atm, conf = _detect_atmosphere("这是一个普通的句子")
        assert atm == "relaxed"
        assert conf == 0.0


class TestDetectEmotion:
    def test_positive_emotion(self) -> None:
        emo, conf = _detect_emotion("太棒了，谢谢！真厉害")
        assert emo == "positive"
        assert conf > 0

    def test_curious_emotion(self) -> None:
        emo, conf = _detect_emotion("这是为什么？怎么回事？")
        assert emo == "curious"
        assert conf > 0

    def test_pressing_emotion(self) -> None:
        emo, conf = _detect_emotion("快点，来不及了，我赶时间")
        assert emo == "pressing"
        assert conf > 0

    def test_negative_low_emotion(self) -> None:
        emo, conf = _detect_emotion("唉，不太行，算了随便吧")
        assert emo == "negative_low"
        assert conf > 0

    def test_negative_high_emotion(self) -> None:
        emo, conf = _detect_emotion("太差了，真让人愤怒！")
        assert emo == "negative_high"
        assert conf > 0

    def test_neutral_emotion_default(self) -> None:
        emo, conf = _detect_emotion("嗯，好的，我看一下")
        assert emo == "neutral"
        assert conf > 0

    def test_no_keyword_defaults_to_neutral(self) -> None:
        emo, conf = _detect_emotion("这是一个普通句子")
        assert emo == "neutral"
        assert conf == 0.0


class TestComputePatience:
    def test_no_decay_at_start(self) -> None:
        p = _compute_patience(0, 0)
        assert p == 1.0

    def test_repeat_decay(self) -> None:
        p = _compute_patience(3, 0)
        assert p == 1.0 - 3 * 0.15

    def test_turn_decay(self) -> None:
        p = _compute_patience(0, 10)
        assert p == 1.0 - 10 * 0.02

    def test_combined_decay(self) -> None:
        p = _compute_patience(2, 5)
        expected = 1.0 - 2 * 0.15 - 5 * 0.02
        assert p == expected

    def test_patience_floor(self) -> None:
        p = _compute_patience(100, 100)
        assert p == 0.1


class TestDetectEmotionTrend:
    def test_short_history_returns_stable(self) -> None:
        history = [{"role": "user", "content": "你好"}]
        assert _detect_emotion_trend(history) == "stable"

    def test_escalating_trend(self) -> None:
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "唉，不太好"},
            {"role": "assistant", "content": "怎么了"},
            {"role": "user", "content": "太差了，真让人生气"},
            {"role": "assistant", "content": "别急"},
            {"role": "user", "content": "烦死了，投诉！"},
        ]
        assert _detect_emotion_trend(history) == "escalating"

    def test_de_escalating_trend(self) -> None:
        history = [
            {"role": "user", "content": "太差了"},
            {"role": "assistant", "content": "抱歉"},
            {"role": "user", "content": "谢谢，你好厉害"},
            {"role": "assistant", "content": "不客气"},
            {"role": "user", "content": "真的太棒了"},
            {"role": "assistant", "content": "很高兴"},
            {"role": "user", "content": "赞，厉害！"},
        ]
        assert _detect_emotion_trend(history) == "de_escalating"

    def test_stable_trend(self) -> None:
        history = [
            {"role": "user", "content": "嗯，可以的"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "明白了"},
            {"role": "assistant", "content": "嗯"},
            {"role": "user", "content": "好的，谢谢"},
            {"role": "assistant", "content": "不客气"},
            {"role": "user", "content": "知道了"},
        ]
        assert _detect_emotion_trend(history) == "stable"


class TestPerceive:
    def test_basic_perception(self) -> None:
        result = perceive(
            user_message="你好，今天怎么样",
            conversation_history=[],
            persona_id="test_persona",
        )
        assert result.conversation_turn == 0
        assert result.repeat_count == 0
        assert result.patience_level == 1.0
        assert result.emotion_trend == "stable"

    def test_perception_with_positive_emotion(self) -> None:
        result = perceive(
            user_message="太棒了，谢谢你的帮助！真厉害",
            conversation_history=[],
            persona_id="test_persona",
        )
        assert result.user_emotion_hint == "positive"
        assert result.user_emotion_confidence > 0

    def test_perception_with_pressing_atmosphere(self) -> None:
        result = perceive(
            user_message="快点，来不及了，立刻帮我处理",
            conversation_history=[],
            persona_id="test_persona",
        )
        assert result.atmosphere == "pressing"
        assert result.atmosphere_confidence > 0

    def test_perception_with_repeat_detection(self) -> None:
        history = [
            {"role": "user", "content": "帮我查资料"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "帮我查资料"},
        ]
        result = perceive(
            user_message="帮我查资料",
            conversation_history=history,
            persona_id="test_persona",
        )
        assert result.repeat_count >= 1

    def test_perception_patience_decay(self) -> None:
        history = [
            {"role": "user", "content": "你好" + str(i)} for i in range(5)
        ]
        result = perceive(
            user_message="再问一次",
            conversation_history=history,
            persona_id="test_persona",
        )
        assert result.conversation_turn == 5
        assert result.patience_level < 1.0

    def test_perception_curious_emotion_trend_stable(self) -> None:
        history = [
            {"role": "user", "content": "为什么"},
            {"role": "assistant", "content": "因为"},
            {"role": "user", "content": "怎么理解"},
            {"role": "assistant", "content": "这样理解"},
            {"role": "user", "content": "原理是什么"},
            {"role": "assistant", "content": "原理是"},
        ]
        result = perceive(
            user_message="什么意思",
            conversation_history=history,
            persona_id="test_persona",
        )
        assert result.user_emotion_hint == "curious"

    def test_perception_summary(self) -> None:
        result = perceive(
            user_message="你好",
            conversation_history=[],
            persona_id="test_persona",
        )
        assert "对话轮次" in result.perception_summary
        assert "氛围" in result.perception_summary
        assert "用户情绪" in result.perception_summary

    def test_perception_with_style_profile(self) -> None:
        style = {"formality": 0.8, "warmth": 0.6}
        result = perceive(
            user_message="请帮我查一下资料",
            conversation_history=[],
            persona_id="test_persona",
            style_profile=style,
        )
        assert result.user_emotion_hint == "neutral"
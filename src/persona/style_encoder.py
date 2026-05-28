from __future__ import annotations

import re

from src.persona.profile import StyleDimensions


class StyleEncoder:
    def encode(self, text: str) -> StyleDimensions:

        text_len = len(text)
        exclamation = text.count("！") + text.count("!")
        question = text.count("？") + text.count("?")
        period = text.count("。") + text.count(".") + text.count("\n")
        text.count("，") + text.count(",")

        formality = min(self._calc_formality(text, exclamation, period), 1.0)
        warmth = min(self._calc_warmth(text, exclamation), 1.0)
        directness = min(self._calc_directness(text, question, exclamation), 1.0)
        playfulness = min(self._calc_playfulness(text, exclamation, question), 1.0)
        detail_orientation = min(self._calc_detail(text, text_len), 1.0)
        emotional_expression = min(self._calc_emotional(text, exclamation, question, text_len), 1.0)
        pace = min(self._calc_pace(text, period), 1.0)

        return StyleDimensions(
            formality=formality,
            warmth=warmth,
            directness=directness,
            playfulness=playfulness,
            detail_orientation=detail_orientation,
            emotional_expression=emotional_expression,
            pace=pace,
        )

    @staticmethod
    def _calc_formality(text: str, exclamation: int, period: int) -> float:
        formal_markers = ["您好", "尊敬的", "请", "感谢", "兹", "根据"]
        informal_markers = ["哈哈", "嗯嗯", "好吧", "呗", "哦哦"]
        formal_score = sum(m in text for m in formal_markers)
        informal_score = sum(m in text for m in informal_markers)
        total = formal_score + informal_score
        if total == 0:
            return 0.5 + min(exclamation * 0.02, 0.3)
        return formal_score / total

    @staticmethod
    def _calc_warmth(text: str, exclamation: int) -> float:
        warm_markers = ["谢谢", "感谢", "加油", "别担心", "祝", "开心", "喜欢", "关心"]
        score = sum(m in text for m in warm_markers)
        return min(score * 0.15 + exclamation * 0.02, 1.0)

    @staticmethod
    def _calc_directness(text: str, question: int, exclamation: int) -> float:
        direct_markers = ["必须", "一定", "绝对", "不行", "可以", "确定", "明确"]
        indirect_markers = ["也许", "可能", "或许", "大概", "我觉得", "似乎", "有点"]
        direct_score = sum(m in text for m in direct_markers)
        indirect_score = sum(m in text for m in indirect_markers)
        total = direct_score + indirect_score
        if total == 0:
            return 0.5 + min(question * 0.03, 0.3)
        return direct_score / total

    @staticmethod
    def _calc_playfulness(text: str, exclamation: int, question: int) -> float:
        playful_markers = ["哈哈", "嘻嘻", "😊", "～", "~", "好玩", "有趣", "开玩笑"]
        score = sum(m in text for m in playful_markers)
        return min(score * 0.15 + min(exclamation * 0.03, 0.2), 1.0)

    @staticmethod
    def _calc_detail(text: str, text_len: int) -> float:
        nums = sum(c.isdigit() for c in text)
        specs = len(re.findall(r'[：:]["「」【】（）()]', text))  # noqa: E501
        return min(nums / max(text_len, 1) * 5 + specs * 0.1, 1.0)

    @staticmethod
    def _calc_emotional(text: str, exclamation: int, question: int, text_len: int) -> float:
        emotional_markers = ["太", "真", "非常", "特别", "超级", "极其"]
        marker_count = sum(m in text for m in emotional_markers)
        return min((exclamation * 0.1 + question * 0.05 + marker_count * 0.1), 1.0)

    @staticmethod
    def _calc_pace(text: str, period: int) -> float:
        sentences = period + 1
        words = len(text) / 1.5
        if sentences == 0:
            return 0.5
        avg_len = words / sentences
        if avg_len < 10:
            return 1.0
        if avg_len > 30:
            return 0.2
        return 1.0 - (avg_len - 10) / 25



from __future__ import annotations

import pytest

from src.persona.style.style_encoder import StyleEncoder, StyleProfile


class TestStyleEncoder:
    def setup_method(self) -> None:
        self.encoder = StyleEncoder()

    def test_encode_returns_style_profile(self) -> None:
        profile = self.encoder.encode("你好，这是一个测试文本。请问有什么可以帮您？谢谢！")
        assert isinstance(profile, StyleProfile)
        assert profile.style_type in StyleEncoder.STYLE_TYPES

    def test_encode_from_string_auto_extracts(self) -> None:
        profile = self.encoder.encode("这是一个测试文本，用于验证编码器功能。")
        assert isinstance(profile, StyleProfile)
        assert profile.raw_result is not None
        assert profile.raw_result.num_words > 0

    def test_formal_dimension_high_with_formal_text(self) -> None:
        profile = self.encoder.encode("您好，尊敬的客户，请根据相关规定办理，感谢配合")
        assert profile.dimensions["formal"].value > 0.3

    def test_formal_dimension_low_with_informal_text(self) -> None:
        profile = self.encoder.encode("哈哈，嗯嗯，好吧，就这样呗")
        assert profile.dimensions["formal"].value < 0.6

    def test_colloquial_dimension_high_with_casual_text(self) -> None:
        profile = self.encoder.encode("哈哈，嘻嘻，这个真好玩～加油！冲！")
        assert profile.dimensions["colloquial"].value > 0.2

    def test_concise_dimension_with_short_sentences(self) -> None:
        profile = self.encoder.encode("好的。可以。知道了。谢谢。再见。")
        concise_val = profile.dimensions["concise"].value
        assert concise_val > 0.0

    def test_expressive_dimension_with_diverse_text(self) -> None:
        profile = self.encoder.encode(
            "太棒了！真厉害！非常满意！超级好用！加油加油！"
        )
        assert profile.dimensions["expressive"].value > 0.0

    def test_emotional_dimension_with_exclamation(self) -> None:
        profile = self.encoder.encode("太棒了！真厉害！非常满意！超级好用！")
        assert profile.dimensions["emotional"].value > 0.1

    def test_all_seven_dimensions_present(self) -> None:
        profile = self.encoder.encode("你好，这是一个测试文本。请问有什么可以帮您？谢谢！")
        expected_keys = {
            "colloquial", "formal", "emotional", "interactive",
            "logical", "concise", "expressive",
        }
        assert set(profile.dimensions.keys()) == expected_keys

    def test_all_dimension_values_in_range(self) -> None:
        profile = self.encoder.encode("你好，这是一个测试文本。请问有什么可以帮您？谢谢！")
        for dim in profile.dimensions.values():
            assert 0.0 <= dim.value <= 1.0

    def test_encode_empty_text_returns_valid_profile(self) -> None:
        profile = self.encoder.encode("")
        assert isinstance(profile, StyleProfile)
        for dim in profile.dimensions.values():
            assert 0.0 <= dim.value <= 1.0

    def test_overall_score_is_computed(self) -> None:
        profile = self.encoder.encode("这是一个合理的测试文本，内容长度适中。")
        assert 0.0 <= profile.overall_score <= 1.0

    def test_confidence_is_computed(self) -> None:
        profile = self.encoder.encode("这是一个测试文本，包含多个句子。这是第二句。这是第三句。")
        assert 0.0 <= profile.confidence <= 1.0
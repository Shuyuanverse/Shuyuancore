from __future__ import annotations

import pytest

from src.persona.style_encoder import StyleEncoder


class TestStyleEncoder:
    def setup_method(self) -> None:
        self.encoder = StyleEncoder()

    def test_formality_high_with_formal_markers(self) -> None:
        dims = self.encoder.encode("您好，尊敬的客户，请根据相关规定办理，感谢配合")
        assert dims.formality > 0.5

    def test_formality_low_with_informal_markers(self) -> None:
        dims = self.encoder.encode("哈哈，嗯嗯，好吧，就这样呗")
        assert dims.formality < 0.5

    def test_warmth_high_with_warm_markers(self) -> None:
        dims = self.encoder.encode("谢谢你的帮助，感谢支持，加油！祝你开心！")
        assert dims.warmth > 0.5

    def test_directness_high_with_direct_markers(self) -> None:
        dims = self.encoder.encode("必须这样做，一定不行，绝对确定")
        assert dims.directness > 0.5

    def test_playfulness_detected(self) -> None:
        dims = self.encoder.encode("哈哈，嘻嘻，这个真好玩～😊")
        assert dims.playfulness > 0.5

    def test_detail_orientation_with_numbers(self) -> None:
        dims = self.encoder.encode("价格是123.45元，数量为678个，总价是9.99")
        assert dims.detail_orientation > 0.5

    def test_emotional_expression_with_exclamation(self) -> None:
        dims = self.encoder.encode("太棒了！真厉害！非常满意！超级好用！")
        assert dims.emotional_expression > 0.5

    def test_pace_fast_with_short_sentences(self) -> None:
        dims = self.encoder.encode("好的。可以。知道了。谢谢。再见。")
        assert dims.pace > 0.5

    def test_pace_slow_with_long_sentences(self) -> None:
        long_text = "这是一个非常长的句子" * 10 + "。"
        for _ in range(5):
            long_text += "这是一个非常长的用于测试节奏的句子，它包含了很多字和很多意思。" * 5 + "。"
        dims = self.encoder.encode(long_text)
        assert dims.pace < 0.8

    def test_empty_text_returns_defaults(self) -> None:
        dims = self.encoder.encode("")
        assert dims.formality == 0.5
        assert dims.warmth == 0.0
        assert dims.directness == 0.5
        assert dims.playfulness == 0.0
        assert dims.detail_orientation == 0.0
        assert dims.emotional_expression == 0.0
        assert dims.pace == 1.0

    def test_all_dimensions_are_floats_in_range(self) -> None:
        dims = self.encoder.encode("你好，这是一个测试文本。请问有什么可以帮您？谢谢！")
        for val in [
            dims.formality, dims.warmth, dims.directness,
            dims.playfulness, dims.detail_orientation,
            dims.emotional_expression, dims.pace,
        ]:
            assert 0.0 <= val <= 1.0

    def test_balanced_text_produces_mid_range_values(self) -> None:
        dims = self.encoder.encode("我觉得这个问题可能有点复杂，也许我们需要考虑几个因素。大概就是这样。")
        assert dims.directness == 0.0

    def test_playfulness_with_tilde(self) -> None:
        dims = self.encoder.encode("这个好好玩～好有趣～嘻嘻～")
        assert dims.playfulness > 0.3
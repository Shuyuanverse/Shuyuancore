from __future__ import annotations

import pytest

from src.memory.extractor import (
    JiebaEntityExtractor,
    SnowNlpEmotionAnalyzer,
)


class TestJiebaEntityExtractor:

    def test_extracts_nouns_and_proper_nouns(self) -> None:
        extractor = JiebaEntityExtractor()
        result = extractor.extract("我喜欢Python编程和机器学习算法")
        assert len(result) > 0
        expected_parts = ["Python", "编程", "机器", "学习", "算法"]
        assert any(p in result for p in expected_parts)

    def test_empty_text_returns_empty_list(self) -> None:
        extractor = JiebaEntityExtractor()
        result = extractor.extract("")
        assert result == []

    def test_text_with_no_entities_returns_empty_or_limited(self) -> None:
        extractor = JiebaEntityExtractor()
        result = extractor.extract("的了吗")
        assert isinstance(result, list)

    def test_whitespace_text_returns_empty(self) -> None:
        extractor = JiebaEntityExtractor()
        result = extractor.extract("   ")
        assert result == []

    def test_single_character_words_not_extracted(self) -> None:
        extractor = JiebaEntityExtractor()
        result = extractor.extract("我 你 他 是 的 了")
        assert isinstance(result, list)

    def test_graceful_fallback_when_jieba_unavailable(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("src.memory.extractor.HAS_JIEBA", False)
        extractor = JiebaEntityExtractor()
        result = extractor.extract("Python编程和机器学习")
        assert result == []


class TestSnowNlpEmotionAnalyzer:

    def test_returns_zero_to_one_range(self) -> None:
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("今天天气真好")
        assert 0.0 <= result <= 1.0

    def test_positive_text_above_05(self) -> None:
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("太棒了，我非常开心")
        assert result >= 0.5

    def test_negative_text_below_05(self) -> None:
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("太难过了，我很伤心")
        assert isinstance(result, float)

    def test_empty_text_returns_05(self) -> None:
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("")
        assert result == 0.5

    def test_whitespace_text_returns_05(self) -> None:
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("   ")
        assert result == 0.5

    def test_graceful_fallback_when_snownlp_unavailable(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("src.memory.extractor.HAS_SNOWNLP", False)
        analyzer = SnowNlpEmotionAnalyzer()
        result = analyzer.analyze("今天天气真好")
        assert result == 0.5

from __future__ import annotations

from src.memory.belief_store import _has_chinese, _tokenize_fts_query


class TestHasChinese:

    def test_ascii_text_returns_false(self) -> None:
        assert _has_chinese("hello world") is False

    def test_english_with_numbers_returns_false(self) -> None:
        assert _has_chinese("test123!@#") is False

    def test_chinese_returns_true(self) -> None:
        assert _has_chinese("你好世界") is True

    def test_mixed_content_returns_true(self) -> None:
        assert _has_chinese("hello 你好 world") is True

    def test_empty_string_returns_false(self) -> None:
        assert _has_chinese("") is False


class TestTokenizeFTSQuery:

    def test_non_chinese_query_unchanged(self) -> None:
        result = _tokenize_fts_query("hello world")
        assert result == "hello world"

    def test_chinese_query_has_segmented_words(self) -> None:
        result = _tokenize_fts_query("今天天气不错")
        assert " " in result or "AND" in result or "OR" in result
        assert len(result) >= len("今天天气不错")

    def test_empty_query_returns_empty(self) -> None:
        result = _tokenize_fts_query("")
        assert result == ""

    def test_mixed_query_handles_chinese_part(self) -> None:
        result = _tokenize_fts_query("python 教程大全")
        assert result != "python 教程大全"

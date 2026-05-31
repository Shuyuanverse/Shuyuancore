from __future__ import annotations

from typing import Any

from src.core.reader import estimate_tokens


class TestEstimateTokens:

    def test_short_text_returns_reasonable_count(self) -> None:
        count = estimate_tokens("Hello world")
        assert count >= 1
        assert count < 10

    def test_long_text_is_proportional(self) -> None:
        short = estimate_tokens("Hello world")
        long = estimate_tokens("Hello world! " * 100)
        assert long > short

    def test_chinese_text(self) -> None:
        count = estimate_tokens("你好世界，这是一段中文测试文本。")
        assert count >= 1

    def test_empty_text(self) -> None:
        count = estimate_tokens("")
        assert count == 1

    def test_fallback_when_tiktoken_unavailable(self, monkeypatch: Any) -> None:
        import src.core.reader as reader_mod

        monkeypatch.setattr(reader_mod, "_ENCODING_CACHE", {})
        monkeypatch.setattr(
            "src.core.reader._get_encoding", lambda model=None: None
        )
        count = estimate_tokens("Hello world test")
        assert count == max(1, len("Hello world test") // 4)

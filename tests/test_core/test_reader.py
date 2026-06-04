from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.interfaces import Belief
from src.core.reader import Reader, estimate_tokens


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


class TestReaderEvidenceBeliefContext:

    @pytest.mark.asyncio
    async def test_read_prefers_evidence_belief_context(self) -> None:
        store = AsyncMock()
        store.get = AsyncMock(return_value=[])
        store.retrieve_evidence_belief_context = AsyncMock(
            return_value={
                "context": "Evidence Ledger:\n- [E-1] user fact",
                "diagnostics": {"retrieved_evidence_count": 1},
            }
        )

        result = await Reader(store).read("conv_1", user_query="fact")

        assert result == [
            {
                "role": "system",
                "content": (
                    "Evidence Ledger:\n- [E-1] user fact\n\n"
                    "Retrieval diagnostics: {'retrieved_evidence_count': 1}"
                ),
            }
        ]
        store.retrieve_evidence_belief_context.assert_awaited_once_with(
            conversation_id="conv_1",
            query="fact",
            max_tokens=4000,
            rescue=False,
        )
        store.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_read_falls_back_when_no_real_ebl_method(self) -> None:
        belief = Belief(
            id="b1",
            content="fallback content",
            source="user",
            timestamp=1000,
            last_accessed=1000,
        )
        store = AsyncMock()
        store.get = AsyncMock(return_value=[belief])

        result = await Reader(store).read("conv_1", user_query="fallback")

        assert result == [{"role": "user", "content": "fallback content"}]
        store.get.assert_awaited_once_with("conv_1")

    @pytest.mark.asyncio
    async def test_read_rescue_passes_rescue_flag(self) -> None:
        store = AsyncMock()
        store.retrieve_evidence_belief_context = AsyncMock(
            return_value={
                "context": "Evidence Ledger:\n- [E-2] rescued fact",
                "diagnostics": {"unknown_rescued": True},
            }
        )

        result = await Reader(store).read_rescue("conv_1", "rescued")

        assert "rescued fact" in result[0]["content"]
        store.retrieve_evidence_belief_context.assert_awaited_once_with(
            conversation_id="conv_1",
            query="rescued",
            max_tokens=6000,
            rescue=True,
        )

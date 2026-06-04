from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.memory.reader import BeliefReader


class TestBeliefReaderEvidenceBeliefContext:

    @pytest.mark.asyncio
    async def test_prefers_evidence_belief_context_when_available(self) -> None:
        store = AsyncMock()
        store.get = AsyncMock(return_value=[])
        store.retrieve_evidence_belief_context = AsyncMock(
            return_value={
                "context": "Evidence Ledger:\n- [E-1] grounded memory",
                "diagnostics": {"retrieved_evidence_count": 1},
            }
        )

        reader = BeliefReader(store)
        result = await reader.read("conv_populated", user_query="grounded")

        assert result[0]["role"] == "system"
        assert "grounded memory" in result[0]["content"]
        store.retrieve_evidence_belief_context.assert_awaited_once_with(
            conversation_id="conv_populated",
            query="grounded",
            max_tokens=4000,
            rescue=False,
        )
        store.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_read_rescue_uses_rescue_stage(self) -> None:
        store = AsyncMock()
        store.retrieve_evidence_belief_context = AsyncMock(
            return_value={
                "context": "Evidence Ledger:\n- [E-2] rescue memory",
                "diagnostics": {"unknown_rescued": True},
            }
        )

        reader = BeliefReader(store)
        result = await reader.read_rescue("conv_populated", "rescue")

        assert "rescue memory" in result[0]["content"]
        store.retrieve_evidence_belief_context.assert_awaited_once_with(
            conversation_id="conv_populated",
            query="rescue",
            max_tokens=6000,
            rescue=True,
        )

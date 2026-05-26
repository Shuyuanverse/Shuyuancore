from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.memory.embedding import EmbeddingService
from src.models.interfaces import EmbeddingResult


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock()
    return provider


class TestEmbeddingService:

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, mock_provider: MagicMock) -> None:
        mock_provider.embed.return_value = EmbeddingResult(
            vectors=[[0.1, 0.2, 0.3, 0.4]],
            model_used="test-model",
            dimensions=4,
        )
        service = EmbeddingService(model_provider=mock_provider)
        result = await service.embed("hello world")
        assert result == [0.1, 0.2, 0.3, 0.4]
        mock_provider.embed.assert_awaited_once_with(["hello world"])

    @pytest.mark.asyncio
    async def test_embed_no_provider(self) -> None:
        service = EmbeddingService(model_provider=None)
        result = await service.embed("hello world")
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_retry_then_success(self, mock_provider: MagicMock) -> None:
        mock_provider.embed.side_effect = [
            RuntimeError("first attempt failed"),
            EmbeddingResult(
                vectors=[[0.5, 0.6, 0.7, 0.8]],
                model_used="test-model",
                dimensions=4,
            ),
        ]
        service = EmbeddingService(model_provider=mock_provider)
        result = await service.embed("retry test")
        assert result == [0.5, 0.6, 0.7, 0.8]
        assert mock_provider.embed.await_count == 2

    @pytest.mark.asyncio
    async def test_embed_both_attempts_fail(self, mock_provider: MagicMock) -> None:
        mock_provider.embed.side_effect = [
            RuntimeError("first attempt failed"),
            RuntimeError("second attempt failed"),
        ]
        service = EmbeddingService(model_provider=mock_provider)
        result = await service.embed("fail test")
        assert result is None
        assert mock_provider.embed.await_count == 2

    @pytest.mark.asyncio
    async def test_embed_empty_vectors(self, mock_provider: MagicMock) -> None:
        mock_provider.embed.return_value = EmbeddingResult(
            vectors=[],
            model_used="test-model",
            dimensions=4,
        )
        service = EmbeddingService(model_provider=mock_provider)
        result = await service.embed("empty test")
        assert result is None

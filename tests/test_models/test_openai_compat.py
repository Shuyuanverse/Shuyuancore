from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.openai_compat import OllamaProvider, OpenAICompatProvider


@pytest.fixture
def provider() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        api_key="test-key",
        base_url="https://api.openai.test/v1",
        model="gpt-4o",
        embedding_model="text-embedding-3-small",
        timeout=5.0,
        max_retries=1,
    )


@pytest.fixture
def ollama() -> OllamaProvider:
    return OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3",
        timeout=5.0,
        max_retries=1,
    )


class TestOpenAICompatProvider:

    @pytest.mark.asyncio
    async def test_chat_success(self, provider: OpenAICompatProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
            "model": "gpt-4o",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.chat(
                history=[{"role": "user", "content": "hi"}],
            )
        assert result.content == "Hello!"
        assert result.tokens_used == 10

    @pytest.mark.asyncio
    async def test_embed_with_model(self, provider: OpenAICompatProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2], "index": 0}],
            "model": "text-embedding-3-small",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.embed(texts=["hello"])
        assert len(result.vectors) == 1
        assert result.dimensions == 2

    @pytest.mark.asyncio
    async def test_embed_not_configured(self) -> None:
        p = OpenAICompatProvider(
            api_key="test",
            base_url="https://test/v1",
            model="gpt-4o",
            embedding_model=None,
        )
        with pytest.raises(NotImplementedError):
            await p.embed(texts=["hello"])

    @pytest.mark.asyncio
    async def test_check_health_ok(self, provider: OpenAICompatProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "gpt-4o",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            status = await provider.check_health()
        assert status.ok is True

    def test_name(self, provider: OpenAICompatProvider) -> None:
        assert provider.name == "openai_compat"


class TestOllamaProvider:

    @pytest.mark.asyncio
    async def test_chat_success(self, ollama: OllamaProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello from Ollama!"},
            "model": "llama3",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await ollama.chat(
                history=[{"role": "user", "content": "hi"}],
            )
        assert result.content == "Hello from Ollama!"
        assert result.model_used == "llama3"

    @pytest.mark.asyncio
    async def test_embed_not_supported(self, ollama: OllamaProvider) -> None:
        with pytest.raises(NotImplementedError):
            await ollama.embed(texts=["hello"])

    @pytest.mark.asyncio
    async def test_check_health_ok(self, ollama: OllamaProvider) -> None:
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_get = AsyncMock()
            mock_get.status_code = 200
            mock_client.get.return_value = mock_get

            status = await ollama.check_health()
        assert status.ok is True

    @pytest.mark.asyncio
    async def test_check_health_fail(self, ollama: OllamaProvider) -> None:
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = ConnectionError("connection refused")

            status = await ollama.check_health()
        assert status.ok is False
        assert "connection refused" in (status.error or "")

    def test_name(self, ollama: OllamaProvider) -> None:
        assert ollama.name == "ollama"

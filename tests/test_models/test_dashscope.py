from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models.dashscope import DashScopeProvider


@pytest.fixture
def provider() -> DashScopeProvider:
    return DashScopeProvider(
        api_key="test-key",
        base_url="https://dashscope.test/v1",
        model="qwen-max",
        embedding_model="text-embedding-v2",
        timeout=5.0,
        max_retries=1,
    )


class TestDashScopeProvider:

    @pytest.mark.asyncio
    async def test_chat_success(self, provider: DashScopeProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
            "model": "qwen-max",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.chat(
                history=[{"role": "user", "content": "hi"}],
            )
        assert result.content == "Hello!"
        assert result.tokens_used == 10
        assert result.model_used == "qwen-max"
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_with_overrides(self, provider: DashScopeProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Code"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
            "model": "deepseek-chat",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.chat(
                history=[{"role": "user", "content": "write code"}],
                model="deepseek-chat",
                temperature=0.3,
                max_tokens=100,
            )
        assert result.content == "Code"
        assert result.model_used == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_embed_success(self, provider: DashScopeProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ],
            "model": "text-embedding-v2",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.embed(texts=["hello", "world"])
        assert len(result.vectors) == 2
        assert result.vectors[0] == [0.1, 0.2, 0.3]
        assert result.dimensions == 1536

    @pytest.mark.asyncio
    async def test_check_health_ok(self, provider: DashScopeProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "qwen-max",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            status = await provider.check_health()
        assert status.ok is True
        assert status.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_check_health_fail(self, provider: DashScopeProvider) -> None:
        with patch.object(
            provider._client,
            "post",
            side_effect=ConnectionError("connection refused"),
        ):
            status = await provider.check_health()
        assert status.ok is False
        assert "connection refused" in (status.error or "")

    def test_name(self, provider: DashScopeProvider) -> None:
        assert provider.name == "dashscope"

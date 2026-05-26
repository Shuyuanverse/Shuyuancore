from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models.deepseek import DeepSeekProvider


@pytest.fixture
def provider() -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key="test-key",
        base_url="https://api.deepseek.test/v1",
        model="deepseek-chat",
        timeout=5.0,
        max_retries=1,
    )


class TestDeepSeekProvider:

    @pytest.mark.asyncio
    async def test_chat_success(self, provider: DeepSeekProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
            "model": "deepseek-chat",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            result = await provider.chat(
                history=[{"role": "user", "content": "hi"}],
            )
        assert result.content == "Hello!"
        assert result.tokens_used == 10
        assert result.model_used == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_embed_not_supported(self, provider: DeepSeekProvider) -> None:
        with pytest.raises(NotImplementedError):
            await provider.embed(texts=["hello"])

    @pytest.mark.asyncio
    async def test_check_health_ok(self, provider: DeepSeekProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "deepseek-chat",
        }

        with patch.object(provider._client, "post", return_value=mock_response):
            status = await provider.check_health()
        assert status.ok is True

    @pytest.mark.asyncio
    async def test_check_health_fail(self, provider: DeepSeekProvider) -> None:
        with patch.object(
            provider._client,
            "post",
            side_effect=ConnectionError("timeout"),
        ):
            status = await provider.check_health()
        assert status.ok is False
        assert "timeout" in (status.error or "")

    def test_name(self, provider: DeepSeekProvider) -> None:
        assert provider.name == "deepseek"

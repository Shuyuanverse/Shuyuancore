from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.translate import TranslateTool


class TestTranslateTool:

    def test_translate_get_spec(self) -> None:
        tool = TranslateTool()
        spec = tool.get_spec()
        assert spec.name == "translate"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_translate_validate_empty_text(self) -> None:
        tool = TranslateTool()
        errors = await tool.validate({"text": ""})
        assert len(errors) >= 1
        assert any("text is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_translate_validate_invalid_provider(self) -> None:
        tool = TranslateTool()
        errors = await tool.validate({
            "text": "hello",
            "provider": "invalid_provider",
        })
        assert len(errors) >= 1
        assert any("Invalid provider" in e and "invalid_provider" in e for e in errors)

    @pytest.mark.asyncio
    async def test_translate_execute_google(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[["你好", "hello"]], None, "en"]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        tool = TranslateTool()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({
                "text": "hello",
                "source_lang": "en",
                "target_lang": "zh",
                "provider": "google",
            })
        assert result.success
        assert result.data is not None
        assert result.data["translated_text"] == "你好"
        assert result.data["provider"] == "google"

    @pytest.mark.asyncio
    async def test_translate_execute_deepl_missing_key(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        tool = TranslateTool()
        errors = await tool.validate({
            "text": "hello",
            "provider": "deepl",
        })
        assert len(errors) >= 1
        assert any("DEEPL_API_KEY" in e for e in errors)
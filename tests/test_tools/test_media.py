from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.media import MediaTool


class TestMediaTool:

    def test_media_get_spec(self) -> None:
        tool = MediaTool()
        spec = tool.get_spec()
        assert spec.name == "media"
        assert spec.category == "extension"

    @pytest.mark.asyncio
    async def test_media_validate_invalid_action(self) -> None:
        tool = MediaTool()
        errors = await tool.validate({"action": "invalid_action"})
        assert len(errors) >= 1
        assert any("Invalid action" in e and "invalid_action" in e for e in errors)

    @pytest.mark.asyncio
    async def test_media_validate_no_input(self) -> None:
        tool = MediaTool()
        errors = await tool.validate({"action": "image_to_text"})
        assert len(errors) >= 1
        assert any("input_path" in e and "required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_media_execute_tts_no_library(self) -> None:
        tool = MediaTool()
        with patch.dict(
            "sys.modules",
            {"edge_tts": None, "gtts": None},
            clear=False,
        ):
            result = await tool.execute({
                "action": "tts",
                "text": "hello world",
            })

        assert not result.success
        assert "gTTS" in result.error

    @pytest.mark.asyncio
    async def test_media_execute_image_to_text_no_tesseract(self) -> None:
        tool = MediaTool()
        with patch.object(Path, "exists", return_value=True):
            with patch.dict(
                "sys.modules",
                {"pytesseract": None},
                clear=False,
            ):
                result = await tool.execute({
                    "action": "image_to_text",
                    "input_path": "/fake/image.png",
                })

        assert not result.success
        assert "not installed" in result.error
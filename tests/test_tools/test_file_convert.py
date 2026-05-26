from __future__ import annotations

import builtins
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tools.builtin.file_convert import FileConvertTool


class TestFileConvertTool:

    def test_file_convert_get_spec(self) -> None:
        tool = FileConvertTool()
        spec = tool.get_spec()
        assert spec.name == "file_convert"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_file_convert_validate_invalid_action(self) -> None:
        tool = FileConvertTool()
        errors = await tool.validate({
            "action": "html",
            "input_path": "/tmp/test.html",
        })
        assert len(errors) == 1
        assert "action must be one of" in errors[0]

    @pytest.mark.asyncio
    async def test_file_convert_validate_no_input(self) -> None:
        tool = FileConvertTool()
        errors = await tool.validate({
            "action": "pdf_to_text",
        })
        assert len(errors) >= 1
        assert any("input_path is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_file_convert_execute_pdf_to_text_mock(self) -> None:
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Extracted text from PDF page"
        mock_doc.load_page.return_value = mock_page
        mock_doc.__len__.return_value = 1
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(b"%PDF-1.4 mock content")
                f.flush()
                tool = FileConvertTool()
                result = await tool.execute({
                    "action": "pdf_to_text",
                    "input_path": f.name,
                })
            assert result.success
            assert "Extracted text from PDF page" in result.data["text"]
            assert result.data["length"] > 0

    @pytest.mark.asyncio
    async def test_file_convert_execute_ocr_not_installed(self) -> None:
        tool = FileConvertTool()
        real_import = builtins.__import__

        def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pytesseract":
                raise ImportError(f"No module named {name!r}")
            return real_import(name, globals, locals, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                f.write(b"PNG mock data")
                f.flush()
                result = await tool.execute({
                    "action": "ocr_image",
                    "input_path": f.name,
                })
            assert not result.success
            assert "pytesseract" in result.error
from __future__ import annotations

import builtins
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.tools.builtin.doc_gen import DocGenTool


class TestDocGenTool:

    def test_doc_gen_get_spec(self) -> None:
        tool = DocGenTool()
        spec = tool.get_spec()
        assert spec.name == "doc_gen"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_doc_gen_validate_invalid_action(self) -> None:
        tool = DocGenTool()
        errors = await tool.validate({
            "action": "html",
            "content": "some content",
            "output_path": "/tmp/output.html",
        })
        assert len(errors) == 1
        assert "action must be one of" in errors[0]

    @pytest.mark.asyncio
    async def test_doc_gen_validate_no_content(self) -> None:
        tool = DocGenTool()
        errors = await tool.validate({
            "action": "markdown",
            "output_path": "/tmp/output.md",
        })
        assert len(errors) >= 1
        assert any("content is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_doc_gen_execute_markdown(self) -> None:
        content = "# Test Document\n\nHello from ShuyuanCore."
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = str(Path(tmp_dir) / "test_output.md")
            tool = DocGenTool()
            result = await tool.execute({
                "action": "markdown",
                "content": content,
                "output_path": output_path,
            })
            assert result.success
            assert result.data["output_path"] == output_path
            written = Path(output_path).read_text(encoding="utf-8")
            assert written == content

    @pytest.mark.asyncio
    async def test_doc_gen_execute_pdf_no_reportlab(self) -> None:
        tool = DocGenTool()
        real_import = builtins.__import__

        def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "reportlab":
                raise ImportError(f"No module named {name!r}")
            if fromlist and any(
                isinstance(m, str) and m.startswith("reportlab")
                for m in (fromlist or [])
            ):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, globals, locals, fromlist, level)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = str(Path(tmp_dir) / "test.pdf")
            with patch.object(builtins, "__import__", side_effect=mock_import):
                result = await tool.execute({
                    "action": "pdf",
                    "content": "PDF content",
                    "output_path": output_path,
                    "title": "Test PDF",
                })
            assert not result.success
            assert "reportlab" in result.error
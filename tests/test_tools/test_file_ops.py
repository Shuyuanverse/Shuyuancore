from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.file_ops import FileOpsTool


class TestFileOpsTool:

    def test_file_ops_get_spec(self) -> None:
        tool = FileOpsTool()
        spec = tool.get_spec()
        assert spec.name == "file_ops"
        assert spec.category == "system"

    @pytest.mark.asyncio
    async def test_file_ops_validate_invalid_op(self) -> None:
        tool = FileOpsTool()
        errors = await tool.validate({
            "operation": "invalid_op",
            "path": "/tmp/test.txt",
        })
        assert len(errors) == 1
        assert "Invalid operation" in errors[0]
        assert "invalid_op" in errors[0]

    @pytest.mark.asyncio
    async def test_file_ops_validate_no_path(self) -> None:
        tool = FileOpsTool()
        errors = await tool.validate({"operation": "read"})
        assert len(errors) >= 1
        assert any("path is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_file_ops_execute_read_success(self) -> None:
        content = "Hello, ShuyuanCore!"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
        ) as f:
            f.write(content)
            temp_path = f.name
        try:
            tool = FileOpsTool()
            result = await tool.execute({
                "operation": "read",
                "path": temp_path,
            })
            assert result.success
            assert result.data == content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_file_ops_execute_write_success(self) -> None:
        content = "Written content for ShuyuanCore"
        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_write"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=True)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
        ) as f:
            temp_path = f.name
        try:
            tool = FileOpsTool()
            with patch(
                "src.tools.builtin.file_ops.get_approval_manager",
                return_value=mock_mgr,
            ):
                result = await tool.execute({
                    "operation": "write",
                    "path": temp_path,
                    "content": content,
                })
            assert result.success
            assert str(Path(temp_path)) in result.data
            actual = Path(temp_path).read_text(encoding="utf-8")
            assert actual == content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_file_ops_execute_delete_dangerous(self) -> None:
        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_test"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=False)

        tool = FileOpsTool()
        with patch(
            "src.tools.builtin.file_ops.get_approval_manager",
            return_value=mock_mgr,
        ):
            result = await tool.execute({
                "operation": "delete",
                "path": "/tmp/nonexistent_test_file",
            })
            assert not result.success
            assert "not approved" in result.error

    @pytest.mark.asyncio
    async def test_file_ops_path_security(self) -> None:
        tool = FileOpsTool()
        errors = await tool.validate({
            "operation": "read",
            "path": ".env",
        })
        assert len(errors) >= 1
        assert any("blocked" in e or "denied" in e for e in errors)

    @pytest.mark.asyncio
    async def test_file_ops_execute_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "alpha.txt").write_text("a", encoding="utf-8")
            (Path(tmp_dir) / "beta.txt").write_text("b", encoding="utf-8")
            (Path(tmp_dir) / "sub").mkdir()
            tool = FileOpsTool()
            result = await tool.execute({
                "operation": "list",
                "path": tmp_dir,
            })
            assert result.success
            entries = result.data["entries"]
            names = [e["name"] for e in entries]
            assert "alpha.txt" in names
            assert "beta.txt" in names
            assert "sub" in names
            assert result.data["count"] == 3
from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.tools.builtin.spreadsheet import SpreadsheetTool


class TestSpreadsheetTool:

    def test_spreadsheet_get_spec(self) -> None:
        tool = SpreadsheetTool()
        spec = tool.get_spec()
        assert spec.name == "spreadsheet"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_spreadsheet_validate_invalid_action(self) -> None:
        tool = SpreadsheetTool()
        errors = await tool.validate({
            "action": "invalid_action",
            "path": "test.csv",
        })
        assert len(errors) >= 1
        assert any("Invalid action" in e and "invalid_action" in e for e in errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_validate_no_path(self) -> None:
        tool = SpreadsheetTool()
        errors = await tool.validate({"action": "read"})
        assert len(errors) >= 1
        assert any("path is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_validate_write_no_data(self) -> None:
        tool = SpreadsheetTool()
        errors = await tool.validate({
            "action": "write",
            "path": "test.csv",
        })
        assert len(errors) >= 1
        assert any("data parameter is required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_spreadsheet_execute_read_csv(self) -> None:
        rows = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["name", "age"])
            writer.writeheader()
            writer.writerows(rows)
            temp_path = f.name
        try:
            tool = SpreadsheetTool()
            result = await tool.execute({
                "action": "read",
                "path": temp_path,
            })
            assert result.success
            assert result.data is not None
            assert result.data["count"] == 2
            assert result.data["rows"] == rows
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_spreadsheet_execute_write_csv(self) -> None:
        data = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False,
        ) as f:
            temp_path = f.name
        try:
            tool = SpreadsheetTool()
            with patch.object(tool, "_is_dangerous", return_value=False):
                result = await tool.execute({
                    "action": "write",
                    "path": temp_path,
                    "data": data,
                })
            assert result.success
            assert result.data is not None
            assert result.data["rows_written"] == 2
            assert result.data["format"] == "csv"

            with open(temp_path, mode="r", newline="") as f:
                reader = csv.DictReader(f)
                written = list(reader)
            assert written == data
        finally:
            Path(temp_path).unlink(missing_ok=True)
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.database import DatabaseTool


class TestDatabaseTool:

    def test_database_get_spec(self) -> None:
        tool = DatabaseTool()
        spec = tool.get_spec()
        assert spec.name == "database"
        assert spec.category == "web"

    @pytest.mark.asyncio
    async def test_database_validate_empty_query(self) -> None:
        tool = DatabaseTool()
        errors = await tool.validate({"query": ""})
        assert len(errors) == 1
        assert "不能为空" in errors[0]

    @pytest.mark.asyncio
    async def test_database_validate_valid(self) -> None:
        tool = DatabaseTool()
        errors = await tool.validate({"query": "SELECT 1"})
        assert errors == []

    @pytest.mark.asyncio
    async def test_database_execute_select(self) -> None:
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[("Alice", 30), ("Bob", 25)],
        )
        mock_cursor.description = [("name",), ("age",)]

        mock_db = AsyncMock()
        mock_db.__aenter__.return_value = mock_db
        mock_db.execute = AsyncMock(return_value=mock_cursor)

        tool = DatabaseTool()
        with patch(
            "src.tools.builtin.database.aiosqlite.connect",
            return_value=mock_db,
        ):
            result = await tool.execute({
                "query": "SELECT name, age FROM users",
                "db_path": ":memory:",
            })

        assert result.success
        assert result.data["count"] == 2
        assert result.data["rows"] == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

    @pytest.mark.asyncio
    async def test_database_execute_write_rejected_readonly(self) -> None:
        tool = DatabaseTool()
        result = await tool.execute({
            "query": "INSERT INTO users (name) VALUES ('test')",
        })

        assert not result.success
        assert "只读" in result.error

    @pytest.mark.asyncio
    async def test_database_execute_write_approved(self) -> None:
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_db = AsyncMock()
        mock_db.__aenter__.return_value = mock_db
        mock_db.execute = AsyncMock(return_value=mock_cursor)

        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_write_test"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.tools.database_readonly = False
        mock_settings.tools.approval_timeout = 300

        tool = DatabaseTool()
        with patch(
            "src.tools.builtin.database.aiosqlite.connect",
            return_value=mock_db,
        ), patch(
            "src.tools.builtin.database.get_approval_manager",
            return_value=mock_mgr,
        ), patch(
            "src.tools.builtin.database.get_settings",
            return_value=mock_settings,
        ):
            result = await tool.execute({
                "query": "INSERT INTO users (name) VALUES ('test')",
                "db_path": ":memory:",
            })

        assert result.success
        assert result.data["affected_rows"] == 1

    @pytest.mark.asyncio
    async def test_database_execute_write_denied(self) -> None:
        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_write_denied"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.tools.database_readonly = False
        mock_settings.tools.approval_timeout = 300

        tool = DatabaseTool()
        with patch(
            "src.tools.builtin.database.get_approval_manager",
            return_value=mock_mgr,
        ), patch(
            "src.tools.builtin.database.get_settings",
            return_value=mock_settings,
        ):
            result = await tool.execute({
                "query": "INSERT INTO users (name) VALUES ('test')",
            })

        assert not result.success
        assert "未获批准" in result.error
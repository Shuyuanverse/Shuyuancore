from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.cron import CronTool


class TestCronTool:

    def test_cron_get_spec(self) -> None:
        tool = CronTool()
        spec = tool.get_spec()
        assert spec.name == "cron"
        assert spec.category == "extension"

    @pytest.mark.asyncio
    async def test_cron_validate_invalid_action(self) -> None:
        tool = CronTool()
        errors = await tool.validate({"action": "invalid_action"})
        assert len(errors) >= 1
        assert any("Invalid action" in e and "invalid_action" in e for e in errors)

    @pytest.mark.asyncio
    async def test_cron_validate_create_no_expression(self) -> None:
        tool = CronTool()
        errors = await tool.validate({
            "action": "create",
            "name": "test_task",
            "task_message": "test message",
        })
        assert len(errors) >= 1
        assert any("cron_expression" in e and "required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_cron_execute_list(self) -> None:
        tool = CronTool()
        result = await tool.execute({"action": "list"})
        assert result.success
        assert result.data is not None
        assert result.data["tasks"] == []
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_cron_execute_create_denied(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "test_approval_id"

        tool = CronTool()
        with patch(
            "src.tools.approval.request_approval",
            AsyncMock(return_value=mock_req),
        ):
            with patch(
                "src.tools.approval.wait_for_approval",
                AsyncMock(return_value=False),
            ):
                result = await tool.execute({
                    "action": "create",
                    "name": "test_task",
                    "cron_expression": "0 8 * * *",
                    "task_message": "test message",
                })

        assert not result.success
        assert "not approved" in result.error
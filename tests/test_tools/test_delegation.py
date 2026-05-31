from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.delegation import DelegationTool


class TestDelegationTool:

    def test_delegation_get_spec(self) -> None:
        tool = DelegationTool()
        spec = tool.get_spec()
        assert spec.name == "delegation"
        assert spec.category == "extension"
        assert spec.dangerous

    @pytest.mark.asyncio
    async def test_delegation_validate_invalid_action(self) -> None:
        tool = DelegationTool()
        errors = await tool.validate({"action": "invalid_action"})
        assert len(errors) >= 1
        assert any("Invalid action" in e and "invalid_action" in e for e in errors)

    @pytest.mark.asyncio
    async def test_delegation_validate_no_description(self) -> None:
        tool = DelegationTool()
        errors = await tool.validate({"action": "delegate"})
        assert len(errors) >= 1
        assert any("task_description" in e and "required" in e for e in errors)

    @pytest.mark.asyncio
    async def test_delegation_execute_check_status(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "test_approval_id"

        tool = DelegationTool()
        with patch(
            "src.tools.approval.request_approval",
            AsyncMock(return_value=mock_req),
        ):
            with patch(
                "src.tools.approval.wait_for_approval",
                AsyncMock(return_value=True),
            ):
                delegate_result = await tool.execute({
                    "action": "delegate",
                    "task_description": "test task",
                })

        assert delegate_result.success
        assert delegate_result.data is not None
        task_id = delegate_result.data["task_id"]
        assert delegate_result.data["status"] == "running"

        status_result = await tool.execute({
            "action": "check_status",
            "task_id": task_id,
        })
        assert status_result.success
        assert status_result.data is not None
        assert status_result.data["status"] == "running"
        assert status_result.data["task_description"] == "test task"

    @pytest.mark.asyncio
    async def test_delegation_execute_delegate_denied(self) -> None:
        mock_req = MagicMock()
        mock_req.approval_id = "test_approval_id"

        tool = DelegationTool()
        with patch(
            "src.tools.approval.request_approval",
            AsyncMock(return_value=mock_req),
        ):
            with patch(
                "src.tools.approval.wait_for_approval",
                AsyncMock(return_value=False),
            ):
                result = await tool.execute({
                    "action": "delegate",
                    "task_description": "test task",
                })

        assert not result.success
        assert "not approved" in result.error
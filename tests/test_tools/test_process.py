from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.tools.builtin.process import ProcessTool


class MockDirEntry:
    def __init__(self, name: str) -> None:
        self.name = name


class TestProcessTool:

    def test_process_get_spec(self) -> None:
        tool = ProcessTool()
        spec = tool.get_spec()
        assert spec.name == "process"
        assert spec.category == "system"
        assert spec.dangerous

    @pytest.mark.asyncio
    async def test_process_validate_invalid_op(self) -> None:
        tool = ProcessTool()
        errors = await tool.validate({"operation": "restart"})
        assert len(errors) == 1
        assert "list 或 kill" in errors[0]

    @pytest.mark.asyncio
    async def test_process_validate_kill_no_pid(self) -> None:
        tool = ProcessTool()
        errors = await tool.validate({"operation": "kill"})
        assert len(errors) >= 1
        assert any("pid" in e for e in errors)

    @pytest.mark.asyncio
    async def test_process_execute_list(self) -> None:
        tool = ProcessTool()
        fake_entries = [MockDirEntry("1"), MockDirEntry("2")]
        with patch("src.tools.builtin.process.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            with patch("os.scandir") as mock_scandir:
                mock_scandir.return_value = fake_entries
                with patch("builtins.open") as mock_open:
                    mock_open.return_value.__enter__.return_value.readlines.side_effect = [
                        ["Name:\tpython\n", "State:\tS (sleeping)\n"],
                        ["Name:\tsshd\n", "State:\tS (sleeping)\n"],
                    ]
                    result = await tool.execute({"operation": "list"})
        assert result.success
        assert result.data["count"] == 2
        names = [p["name"] for p in result.data["processes"]]
        assert "python" in names
        assert "sshd" in names

    @pytest.mark.asyncio
    async def test_process_execute_kill(self) -> None:
        tool = ProcessTool()
        with patch("src.tools.builtin.process.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            with patch("os.kill") as mock_kill:
                mock_kill.return_value = None
                result = await tool.execute({
                    "operation": "kill",
                    "pid": 1234,
                })
        assert result.success
        assert result.data["pid"] == 1234
        assert result.data["signal"] == "SIGTERM"
        assert mock_kill.call_count == 2

    @pytest.mark.asyncio
    async def test_process_execute_kill_not_found(self) -> None:
        tool = ProcessTool()
        with patch("src.tools.builtin.process.get_audit_logger") as mock_audit:
            mock_audit.return_value = MagicMock()
            with patch("os.kill") as mock_kill:
                mock_kill.side_effect = OSError("No such process")
                result = await tool.execute({
                    "operation": "kill",
                    "pid": 99999,
                })
        assert not result.success
        assert "不存在" in result.error
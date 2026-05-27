from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security.sandbox import SandboxResult
from src.tools.builtin.terminal import TerminalTool


class TestTerminalTool:
    def test_terminal_get_spec(self) -> None:
        tool = TerminalTool()
        spec = tool.get_spec()
        assert spec.name == "terminal"
        assert spec.dangerous is True
        assert spec.category == "system"

    @pytest.mark.asyncio
    async def test_terminal_validate_empty_command(self) -> None:
        tool = TerminalTool()
        errors = await tool.validate({"command": ""})
        assert errors == ["command 参数不能为空"]

    @pytest.mark.asyncio
    async def test_terminal_validate_valid(self) -> None:
        tool = TerminalTool()
        errors = await tool.validate({"command": "ls -la"})
        assert errors == []

    @pytest.mark.asyncio
    async def test_terminal_execute_success(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_sandbox.execute_command = AsyncMock(
            return_value=SandboxResult(
                success=True,
                stdout="file1\nfile2",
                stderr="",
                exit_code=0,
            ),
        )
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "ls -la"})

        assert result.success is True
        assert result.data is not None
        assert result.data["stdout"] == "file1\nfile2"

    @pytest.mark.asyncio
    async def test_terminal_execute_failure(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_sandbox.execute_command = AsyncMock(
            return_value=SandboxResult(
                success=False,
                stdout="",
                stderr="cmd not found",
                error="command not found",
                exit_code=127,
            ),
        )
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "invalid_command"})

        assert result.success is False
        assert "command not found" in result.error

    def test_terminal_dangerous_detection(self) -> None:
        tool = TerminalTool()
        assert tool._contains_dangerous_command("rm -rf /") is True
        assert tool._contains_dangerous_command("dd if=/dev/zero of=/dev/sda") is True
        assert tool._contains_dangerous_command("mkfs /dev/sda1") is True
        assert tool._contains_dangerous_command("chmod 777 /etc") is True

    def test_terminal_safe_detection(self) -> None:
        tool = TerminalTool()
        assert tool._contains_dangerous_command("ls -la") is False
        assert tool._contains_dangerous_command("echo hello") is False
        assert tool._contains_dangerous_command("cat /etc/passwd") is False
        assert tool._contains_dangerous_command("grep pattern file") is False

    @pytest.mark.asyncio
    async def test_terminal_sandbox_unavailable_nonwhitelist(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=False)
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "rm -rf /tmp/test"})

        assert result.success is False
        assert "审批" in result.error

    @pytest.mark.asyncio
    async def test_terminal_local_downgrade_whitelist(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=False)
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "echo hello"})

        assert result.success is True
        assert result.data is not None
        assert result.data.get("mode") == "local"
        assert "hello" in result.data.get("stdout", "")

    @pytest.mark.asyncio
    async def test_terminal_local_downgrade_failure(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=False)
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "cat /nonexistent_file_xyz"})

        assert result.success is False
        assert result.data is not None
        assert result.data.get("exit_code", 0) != 0

    def test_terminal_is_whitelisted(self) -> None:
        tool = TerminalTool()
        from src.config import get_settings

        settings = get_settings()
        assert tool._is_whitelisted("ls -la", settings) is True
        assert tool._is_whitelisted("pwd", settings) is True
        assert tool._is_whitelisted("echo hello", settings) is True
        assert tool._is_whitelisted("rm -rf /", settings) is False
        assert tool._is_whitelisted("dd if=/dev/zero of=/dev/sda", settings) is False

    @pytest.mark.asyncio
    async def test_terminal_parse_error(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.terminal.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.terminal.get_audit_logger", return_value=mock_audit),
            patch(
                "src.tools.builtin.terminal.shlex.split",
                side_effect=ValueError("unterminated quote"),
            ),
        ):
            tool = TerminalTool()
            result = await tool.execute({"command": "echo 'hello"})

        assert result.success is False
        assert "命令解析失败" in result.error

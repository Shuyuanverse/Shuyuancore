from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security.sandbox import SandboxResult
from src.tools.builtin.code_exec import CodeExecTool


class TestCodeExecTool:

    def test_code_exec_get_spec(self) -> None:
        tool = CodeExecTool()
        spec = tool.get_spec()
        assert spec.name == "code_exec"
        assert spec.category == "system"
        assert spec.dangerous is True

    @pytest.mark.asyncio
    async def test_code_exec_validate_empty_code(self) -> None:
        tool = CodeExecTool()
        errors = await tool.validate({"code": ""})
        assert "code 参数不能为空" in errors

    @pytest.mark.asyncio
    async def test_code_exec_validate_invalid_language(self) -> None:
        tool = CodeExecTool()
        errors = await tool.validate({"code": "print(1)", "language": "ruby"})
        assert any("不支持" in e for e in errors)

    @pytest.mark.asyncio
    async def test_code_exec_validate_valid(self) -> None:
        tool = CodeExecTool()
        errors = await tool.validate({"code": "print('hello')", "language": "python"})
        assert errors == []

    @pytest.mark.asyncio
    async def test_code_exec_execute_python_success(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_sandbox.execute_code = AsyncMock(
            return_value=SandboxResult(
                success=True, stdout="hello\n", stderr="", exit_code=0,
            ),
        )
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.code_exec.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.code_exec.get_audit_logger", return_value=mock_audit),
        ):
            tool = CodeExecTool()
            result = await tool.execute({"code": "print('hello')"})

        assert result.success is True
        assert result.data is not None
        assert result.data["stdout"] == "hello\n"

    @pytest.mark.asyncio
    async def test_code_exec_execute_javascript_success(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_sandbox.execute_code = AsyncMock(
            return_value=SandboxResult(
                success=True, stdout="ok\n", stderr="", exit_code=0,
            ),
        )
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.code_exec.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.code_exec.get_audit_logger", return_value=mock_audit),
        ):
            tool = CodeExecTool()
            result = await tool.execute({
                "code": "console.log('ok')", "language": "javascript",
            })

        assert result.success is True
        assert result.data is not None
        assert result.data["stdout"] == "ok\n"

    @pytest.mark.asyncio
    async def test_code_exec_execute_failure(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=True)
        mock_sandbox.execute_code = AsyncMock(
            return_value=SandboxResult(
                success=False, stdout="", stderr="NameError: name 'x' is not defined",
                error="execution error", exit_code=1,
            ),
        )
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.code_exec.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.code_exec.get_audit_logger", return_value=mock_audit),
        ):
            tool = CodeExecTool()
            result = await tool.execute({"code": "print(x)"})

        assert result.success is False
        assert "execution error" in result.error

    @pytest.mark.asyncio
    async def test_code_exec_sandbox_unavailable(self) -> None:
        mock_sandbox = MagicMock()
        mock_sandbox.check_available = AsyncMock(return_value=False)
        mock_audit = MagicMock()

        with (
            patch("src.tools.builtin.code_exec.ToolSandbox", return_value=mock_sandbox),
            patch("src.tools.builtin.code_exec.get_audit_logger", return_value=mock_audit),
        ):
            tool = CodeExecTool()
            result = await tool.execute({"code": "print('hello')"})

        assert result.success is False
        assert "Docker 沙箱不可用" in result.error
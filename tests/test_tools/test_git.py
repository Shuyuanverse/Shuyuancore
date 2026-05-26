from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.git import GitTool


def _make_completed_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestGitTool:

    def test_git_get_spec(self) -> None:
        tool = GitTool()
        spec = tool.get_spec()
        assert spec.name == "git"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_git_validate_invalid_action(self) -> None:
        tool = GitTool()
        errors = await tool.validate({"action": "blame"})
        assert len(errors) == 1
        assert "action must be one of" in errors[0]

    @pytest.mark.asyncio
    async def test_git_validate_commit_no_message(self) -> None:
        tool = GitTool()
        errors = await tool.validate({"action": "commit"})
        assert len(errors) == 1
        assert "commit operation requires message" in errors[0]

    @pytest.mark.asyncio
    async def test_git_execute_status(self) -> None:
        mock_audit = MagicMock()
        mock_process = _make_completed_process(
            stdout=" M src/tool.py\n?? new_file.txt\n",
        )

        tool = GitTool()
        with patch(
            "src.tools.builtin.git.get_audit_logger", return_value=mock_audit,
        ):
            with patch(
                "src.tools.builtin.git.subprocess.run",
                return_value=mock_process,
            ) as mock_run:
                result = await tool.execute({
                    "action": "status",
                    "repo_path": "/fake/repo",
                })

        assert result.success
        assert " M src/tool.py" in result.data["stdout"]
        assert "?? new_file.txt" in result.data["stdout"]
        assert result.data["returncode"] == 0
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert kwargs["cwd"] == "/fake/repo"

    @pytest.mark.asyncio
    async def test_git_execute_log(self) -> None:
        log_output = (
            "a1b2c3d feat: add user login\n"
            "e4f5g6h fix: correct timeout value\n"
            "i7j8k9l chore: update dependencies\n"
        )
        mock_audit = MagicMock()
        mock_process = _make_completed_process(stdout=log_output)

        tool = GitTool()
        with patch(
            "src.tools.builtin.git.get_audit_logger", return_value=mock_audit,
        ):
            with patch(
                "src.tools.builtin.git.subprocess.run",
                return_value=mock_process,
            ) as mock_run:
                result = await tool.execute({
                    "action": "log",
                    "repo_path": "/fake/repo",
                })

        assert result.success
        assert "a1b2c3d" in result.data["stdout"]
        assert "e4f5g6h" in result.data["stdout"]
        assert "i7j8k9l" in result.data["stdout"]
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "log" in call_args
        assert "--oneline" in call_args

    @pytest.mark.asyncio
    async def test_git_execute_push_requires_approval(self) -> None:
        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_git_push"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=False)

        mock_audit = MagicMock()

        tool = GitTool()
        with patch(
            "src.tools.builtin.git.get_approval_manager",
            return_value=mock_mgr,
        ):
            with patch(
                "src.tools.builtin.git.get_audit_logger",
                return_value=mock_audit,
            ):
                result = await tool.execute({
                    "action": "push",
                    "repo_path": "/fake/repo",
                })

        assert not result.success
        assert "not approved" in result.error
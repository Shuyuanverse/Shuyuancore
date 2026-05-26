from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.project_mgmt import ProjectMgmtTool


class TestProjectMgmtTool:

    def test_project_mgmt_get_spec(self) -> None:
        tool = ProjectMgmtTool()
        spec = tool.get_spec()
        assert spec.name == "project_mgmt"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_project_mgmt_validate_invalid_provider(self) -> None:
        tool = ProjectMgmtTool()
        errors = await tool.validate({
            "provider": "gitlab",
            "action": "list_issues",
        })
        assert len(errors) >= 1
        assert any(
            "provider must be one of" in e and "github" in e and "jira" in e
            for e in errors
        )

    @pytest.mark.asyncio
    async def test_project_mgmt_validate_no_action(self) -> None:
        tool = ProjectMgmtTool()
        errors = await tool.validate({
            "provider": "github",
            "action": "",
        })
        assert len(errors) >= 1
        assert any("action must be one of" in e for e in errors)

    @pytest.mark.asyncio
    async def test_project_mgmt_execute_github_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 1,
                "title": "Fix login bug",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [{"name": "bug"}],
                "created_at": "2026-05-01T00:00:00Z",
                "html_url": "https://github.com/owner/repo/issues/1",
            },
            {
                "number": 2,
                "title": "Add docs",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [],
                "created_at": "2026-05-02T00:00:00Z",
                "html_url": "https://github.com/owner/repo/issues/2",
            },
        ]

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        tool = ProjectMgmtTool()
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({
                "provider": "github",
                "action": "list_issues",
                "repo": "owner/repo",
            })

        assert result.success
        assert result.data["count"] == 2
        issues = result.data["issues"]
        assert issues[0]["number"] == 1
        assert issues[0]["title"] == "Fix login bug"
        assert issues[1]["number"] == 2
        assert issues[1]["title"] == "Add docs"

    @pytest.mark.asyncio
    async def test_project_mgmt_execute_github_create_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")

        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_create_denied"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=False)

        tool = ProjectMgmtTool()
        with patch(
            "src.tools.builtin.project_mgmt.get_approval_manager",
            return_value=mock_mgr,
        ):
            result = await tool.execute({
                "provider": "github",
                "action": "create_issue",
                "repo": "owner/repo",
                "title": "New bug",
            })

        assert not result.success
        assert "not approved" in result.error

    @pytest.mark.asyncio
    async def test_project_mgmt_execute_jira_no_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

        tool = ProjectMgmtTool()
        result = await tool.execute({
            "provider": "jira",
            "action": "list_issues",
            "project": "TEST",
        })

        assert not result.success
        assert "not configured" in result.error or "environment variable" in result.error.lower()
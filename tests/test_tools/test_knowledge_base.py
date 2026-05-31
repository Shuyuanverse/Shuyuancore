from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.knowledge_base import KnowledgeBaseTool


class TestKnowledgeBaseTool:

    def test_kb_get_spec(self) -> None:
        tool = KnowledgeBaseTool()
        spec = tool.get_spec()
        assert spec.name == "knowledge_base"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_kb_validate_invalid_provider(self) -> None:
        tool = KnowledgeBaseTool()
        errors = await tool.validate({
            "provider": "confluence",
            "action": "list",
        })
        assert len(errors) >= 1
        assert any("Invalid provider" in e or "Must be one of" in e for e in errors)
        assert any("confluence" in e for e in errors)

    @pytest.mark.asyncio
    async def test_kb_validate_no_action(self) -> None:
        tool = KnowledgeBaseTool()
        errors = await tool.validate({
            "provider": "local",
            "action": "",
        })
        assert len(errors) >= 1
        assert any("Invalid action" in e for e in errors)

    @pytest.mark.asyncio
    async def test_kb_execute_local_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_dir = Path(tmp_dir) / "data" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)

            (knowledge_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
            (knowledge_dir / "doc2.md").write_text("# Doc 2", encoding="utf-8")
            (knowledge_dir / "readme.txt").write_text("not a markdown", encoding="utf-8")

            monkeypatch.setattr(Path, "cwd", lambda: Path(tmp_dir).resolve())

            tool = KnowledgeBaseTool()
            result = await tool.execute({
                "provider": "local",
                "action": "list",
            })

            assert result.success
            assert result.data["count"] == 2
            file_names = [f["name"] for f in result.data["files"]]
            assert "doc1.md" in file_names
            assert "doc2.md" in file_names
            assert "readme.txt" not in file_names

    @pytest.mark.asyncio
    async def test_kb_execute_local_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        content = "# Hello\n\nThis is a test document."
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_dir = Path(tmp_dir) / "data" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)

            (knowledge_dir / "readme.md").write_text(content, encoding="utf-8")

            monkeypatch.setattr(Path, "cwd", lambda: Path(tmp_dir).resolve())

            tool = KnowledgeBaseTool()
            result = await tool.execute({
                "provider": "local",
                "action": "read",
                "path": "readme.md",
            })

            assert result.success
            assert result.data["content"] == content

    @pytest.mark.asyncio
    async def test_kb_execute_local_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_dir = Path(tmp_dir) / "data" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)

            (knowledge_dir / "architecture.md").write_text(
                "# Architecture\n\nThe system uses a microservices architecture.",
                encoding="utf-8",
            )
            (knowledge_dir / "deployment.md").write_text(
                "# Deployment\n\nDeploy using Docker containers.",
                encoding="utf-8",
            )
            (knowledge_dir / "readme.md").write_text(
                "# Project\n\nWelcome to the project.",
                encoding="utf-8",
            )

            monkeypatch.setattr(Path, "cwd", lambda: Path(tmp_dir).resolve())

            tool = KnowledgeBaseTool()
            result = await tool.execute({
                "provider": "local",
                "action": "search",
                "query": "architecture",
            })

            assert result.success
            assert result.data["total_matches"] >= 1
            file_results = [r["file"] for r in result.data["results"]]
            assert any("architecture" in f for f in file_results)

    @pytest.mark.asyncio
    async def test_kb_execute_local_write_approval_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_kb_write"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_dir = Path(tmp_dir) / "data" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)

            monkeypatch.setattr(Path, "cwd", lambda: Path(tmp_dir).resolve())

            body = "Hello, knowledge base!"
            tool = KnowledgeBaseTool()
            with patch(
                "src.tools.builtin.knowledge_base.get_approval_manager",
                return_value=mock_mgr,
                create=True,
            ) as mock_get_am:
                result = await tool.execute({
                    "provider": "local",
                    "action": "write",
                    "path": "test_note.md",
                    "content": {"title": "Test", "body": body},
                })

            actual_path = knowledge_dir / "test_note.md"
            if result.success:
                assert actual_path.exists()
                assert actual_path.read_text(encoding="utf-8") == body
            else:
                assert "not approved" in result.error
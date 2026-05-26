from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.skills import SkillsTool


class TestSkillsTool:

    def test_skills_get_spec(self) -> None:
        tool = SkillsTool()
        spec = tool.get_spec()
        assert spec.name == "skills"
        assert spec.category == "skills"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_skills_validate_invalid_op(self) -> None:
        mock_store = MagicMock()
        tool = SkillsTool(store=mock_store)
        errors = await tool.validate({"operation": "invalid_op"})
        assert any("operation 必须是" in e for e in errors)

    @pytest.mark.asyncio
    async def test_skills_validate_missing_name(self) -> None:
        mock_store = MagicMock()
        tool = SkillsTool(store=mock_store)
        errors = await tool.validate({"operation": "get"})
        assert any("必须提供 name 参数" in e for e in errors)

    @pytest.mark.asyncio
    async def test_skills_execute_list(self) -> None:
        mock_store = MagicMock()
        expected_skills = [
            {"name": "skill_a", "content": "content a"},
            {"name": "skill_b", "content": "content b"},
        ]
        mock_store.list_skills = AsyncMock(return_value=expected_skills)
        tool = SkillsTool(store=mock_store)
        with patch("src.tools.builtin.skills.get_audit_logger", return_value=MagicMock()):
            result = await tool.execute({"operation": "list"}, user_id="test_user")

        assert result.success is True
        assert result.data is not None
        assert result.data["count"] == 2
        assert len(result.data["skills"]) == 2
        assert result.data["skills"][0]["name"] == "skill_a"
        mock_store.list_skills.assert_awaited_once_with(status="active")

    @pytest.mark.asyncio
    async def test_skills_execute_create(self) -> None:
        mock_store = MagicMock()
        mock_store.get_skill = AsyncMock(return_value=None)
        mock_store.create_skill = AsyncMock(return_value="new-skill-id")
        tool = SkillsTool(store=mock_store)
        with patch("src.tools.builtin.skills.get_audit_logger", return_value=MagicMock()):
            result = await tool.execute({
                "operation": "create",
                "name": "new_skill",
                "content": "skill content",
                "conversation_id": "conv-1",
            }, user_id="test_user")

        assert result.success is True
        assert result.data is not None
        assert result.data["id"] == "new-skill-id"
        assert result.data["name"] == "new_skill"

    @pytest.mark.asyncio
    async def test_skills_execute_delete(self) -> None:
        mock_store = MagicMock()
        mock_store.get_skill = AsyncMock(
            return_value={"name": "old_skill", "content": "content"},
        )
        mock_store.delete_skill = AsyncMock()
        tool = SkillsTool(store=mock_store)
        with patch("src.tools.builtin.skills.get_audit_logger", return_value=MagicMock()):
            result = await tool.execute(
                {"operation": "delete", "name": "old_skill"},
                user_id="test_user",
            )

        assert result.success is True
        assert result.data is not None
        assert result.data["name"] == "old_skill"
        assert result.data["deleted"] is True
        mock_store.delete_skill.assert_awaited_once_with("old_skill")
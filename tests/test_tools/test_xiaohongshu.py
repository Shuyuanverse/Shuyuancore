from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.xiaohongshu import XiaoHongShuTool


class TestXiaoHongShuTool:

    def test_xhs_get_spec(self) -> None:
        tool = XiaoHongShuTool()
        spec = tool.get_spec()
        assert spec.name == "xiaohongshu"
        assert spec.category == "social"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_xhs_validate_invalid_action(self) -> None:
        tool = XiaoHongShuTool()
        errors = await tool.validate({"action": "delete_note"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "delete_note" in errors[0]

    @pytest.mark.asyncio
    async def test_xhs_validate_no_keyword(self) -> None:
        tool = XiaoHongShuTool()
        errors = await tool.validate({"action": "search_note"})
        assert len(errors) >= 1
        assert any("keyword" in e and "search_note" in e for e in errors)

        errors_empty = await tool.validate({
            "action": "search_note",
            "keyword": "",
        })
        assert len(errors_empty) >= 1
        assert any("keyword" in e and "search_note" in e for e in errors_empty)

    @pytest.mark.asyncio
    async def test_xhs_validate_valid(self) -> None:
        tool = XiaoHongShuTool()
        errors = await tool.validate({
            "action": "search_note",
            "keyword": "Python教程",
            "limit": 5,
            "timeout": 15,
        })
        assert errors == []

    @pytest.mark.asyncio
    async def test_xhs_execute_search_note(self) -> None:
        mock_data: dict[str, Any] = {
            "items": [
                {
                    "note_id": "note_001",
                    "title": "Python教程 - 入门到精通",
                    "author": "编程达人",
                    "likes": 2345,
                    "comments": 89,
                    "summary": "最好的Python入门教程",
                },
                {
                    "note_id": "note_002",
                    "title": "Python教程 - 实战项目",
                    "author": "码农成长记",
                    "likes": 1567,
                    "comments": 67,
                    "summary": "通过实战学习Python",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        tool = XiaoHongShuTool()
        with patch(
            "src.tools.builtin.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute({
                "action": "search_note",
                "keyword": "Python教程",
                "limit": 5,
            })

        assert result.success
        assert result.data is not None
        assert result.data["keyword"] == "Python教程"
        assert len(result.data["notes"]) == 2
        assert result.data["notes"][0]["note_id"] == "note_001"
        assert result.data["notes"][1]["title"] == "Python教程 - 实战项目"
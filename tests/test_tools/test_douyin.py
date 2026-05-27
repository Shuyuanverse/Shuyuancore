from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tools.builtin.douyin import DouYinTool


class TestDouYinTool:
    def test_douyin_get_spec(self) -> None:
        tool = DouYinTool()
        spec = tool.get_spec()
        assert spec.name == "douyin"
        assert spec.category == "social"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_douyin_validate_invalid_action(self) -> None:
        tool = DouYinTool()
        errors = await tool.validate({"action": "delete_video"})
        assert len(errors) == 1
        assert "Invalid action" in errors[0]
        assert "delete_video" in errors[0]

    @pytest.mark.asyncio
    async def test_douyin_validate_no_keyword(self) -> None:
        tool = DouYinTool()
        errors = await tool.validate({"action": "search_video"})
        assert len(errors) >= 1
        assert any("keyword" in e and "search_video" in e for e in errors)

        errors_empty = await tool.validate(
            {
                "action": "search_video",
                "keyword": "",
            }
        )
        assert len(errors_empty) >= 1
        assert any("keyword" in e and "search_video" in e for e in errors_empty)

    @pytest.mark.asyncio
    async def test_douyin_validate_valid(self) -> None:
        tool = DouYinTool()
        errors = await tool.validate(
            {
                "action": "search_video",
                "keyword": "美食制作",
                "limit": 5,
                "timeout": 15,
            }
        )
        assert errors == []

    @pytest.mark.asyncio
    async def test_douyin_execute_search_video(self) -> None:
        mock_data: dict[str, Any] = {
            "data": [
                {
                    "video_id": "video_001",
                    "title": "美食制作 - 家常菜谱",
                    "author": "美食达人1",
                    "likes": 12345,
                    "comments": 678,
                    "shares": 234,
                    "duration": 180,
                    "description": "简单易学的家常菜谱",
                },
                {
                    "video_id": "video_002",
                    "title": "美食制作 - 烘焙教程",
                    "author": "烘焙高手",
                    "likes": 9876,
                    "comments": 543,
                    "shares": 198,
                    "duration": 240,
                    "description": "零失败烘焙教程",
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

        tool = DouYinTool()
        with patch(
            "src.tools.builtin.douyin.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                {
                    "action": "search_video",
                    "keyword": "美食制作",
                    "limit": 5,
                }
            )

        assert result.success
        assert result.data is not None
        assert result.data["keyword"] == "美食制作"
        assert len(result.data["videos"]) == 2
        assert result.data["videos"][0]["video_id"] == "video_001"
        assert result.data["videos"][1]["title"] == "美食制作 - 烘焙教程"

    @pytest.mark.asyncio
    async def test_douyin_execute_search_video_mock_fallback(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        tool = DouYinTool()
        with patch(
            "src.tools.builtin.douyin.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                {
                    "action": "search_video",
                    "keyword": "测试",
                    "limit": 5,
                }
            )

        assert result.success
        assert result.data is not None
        assert result.data.get("source") == "mock"
        assert len(result.data.get("videos", [])) > 0

    @pytest.mark.asyncio
    async def test_douyin_execute_search_video_network_error_fallback(self) -> None:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        tool = DouYinTool()
        with patch(
            "src.tools.builtin.douyin.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute(
                {
                    "action": "search_video",
                    "keyword": "测试",
                    "limit": 5,
                }
            )

        assert result.success
        assert result.data is not None
        assert result.data.get("source") == "mock"
        assert len(result.data.get("videos", [])) > 0

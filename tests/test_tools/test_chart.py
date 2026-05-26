from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.chart import ChartTool
from src.tools.interfaces import ToolResult


class TestChartTool:

    def test_chart_get_spec(self) -> None:
        tool = ChartTool()
        spec = tool.get_spec()
        assert spec.name == "chart"
        assert spec.category == "extension"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_chart_validate_invalid_action(self) -> None:
        tool = ChartTool()
        errors = await tool.validate({"action": "invalid"})
        assert len(errors) == 1
        assert "action must be one of" in errors[0]

    @pytest.mark.asyncio
    async def test_chart_validate_no_data(self) -> None:
        tool = ChartTool()
        errors = await tool.validate({"action": "bar"})
        assert len(errors) == 1
        assert "data" in errors[0]

    @pytest.mark.asyncio
    async def test_chart_execute_mermaid(self) -> None:
        tool = ChartTool()
        result = await tool.execute({
            "action": "mermaid",
            "data": [{"from": "A", "to": "B"}],
            "title": "Flow",
        })
        assert result.success
        assert "graph TD" in result.data["code"]
        assert "A --> B" in result.data["code"]
        assert result.data["type"] == "mermaid"

    @pytest.mark.asyncio
    async def test_chart_execute_bar_matplotlib(self) -> None:
        expected_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAE="

        tool = ChartTool()
        with patch("src.tools.builtin.chart._HAS_MATPLOTLIB", True), \
             patch.object(
                ChartTool, "_generate_bar",
                new=AsyncMock(return_value=ToolResult(
                    success=True,
                    data={"type": "bar", "format": "base64", "image": expected_base64},
                )),
            ):
            result = await tool.execute({
                "action": "bar",
                "data": [{"x": "A", "y": 1}, {"x": "B", "y": 2}],
                "x_field": "x",
                "y_field": "y",
                "title": "Test Bar",
            })

        assert result.success
        assert result.data["type"] == "bar"
        assert result.data["format"] == "base64"
        assert result.data["image"] == expected_base64

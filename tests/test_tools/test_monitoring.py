from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.monitoring import MonitoringTool


class TestMonitoringTool:

    def test_monitoring_get_spec(self) -> None:
        tool = MonitoringTool()
        spec = tool.get_spec()
        assert spec.name == "monitoring"
        assert spec.category == "extension"
        assert spec.dangerous is False

    @pytest.mark.asyncio
    async def test_monitoring_validate_invalid_action(self) -> None:
        tool = MonitoringTool()
        errors = await tool.validate({"action": "invalid"})
        assert len(errors) == 1
        assert "action must be one of" in errors[0]

    @pytest.mark.asyncio
    async def test_monitoring_validate_no_url(self) -> None:
        tool = MonitoringTool()
        errors = await tool.validate({"action": "website_check"})
        assert len(errors) == 1
        assert "url" in errors[0]

    @pytest.mark.asyncio
    async def test_monitoring_execute_website_check(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_instance = MagicMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)

        tool = MonitoringTool()
        with patch("src.tools.builtin.monitoring._HAS_HTTPX", True), \
             patch("src.tools.builtin.monitoring.httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client_instance
            mock_httpx.AsyncClient.return_value.__aexit__.return_value = None

            result = await tool.execute({
                "action": "website_check",
                "url": "https://example.com",
                "timeout": 30,
            })

        assert result.success
        assert result.data["status_code"] == 200
        assert result.data["url"] == "https://example.com"
        assert "response_time_ms" in result.data

    @pytest.mark.asyncio
    async def test_monitoring_execute_ping(self) -> None:
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = (
            "PING example.com (93.184.216.34) 56(84) bytes of data."
        )
        mock_subprocess_result.stderr = ""

        tool = MonitoringTool()
        with patch(
            "src.tools.builtin.monitoring.subprocess.run",
            return_value=mock_subprocess_result,
        ):
            result = await tool.execute({
                "action": "ping",
                "host": "example.com",
                "timeout": 10,
            })

        assert result.success
        assert result.data["host"] == "example.com"
        assert result.data["reachable"] is True
        assert "PING" in result.data["output"]

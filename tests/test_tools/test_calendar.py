from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.tools.builtin.calendar import CalendarTool


class TestCalendarTool:

    def test_calendar_get_spec(self) -> None:
        tool = CalendarTool()
        spec = tool.get_spec()
        assert spec.name == "calendar"
        assert spec.category == "office"

    @pytest.mark.asyncio
    async def test_calendar_validate_invalid_action(self) -> None:
        tool = CalendarTool()
        errors = await tool.validate({"action": "invalid_action"})
        assert len(errors) >= 1
        assert any("action must be one of" in e for e in errors)

    @pytest.mark.asyncio
    async def test_calendar_validate_delete_no_id(self) -> None:
        tool = CalendarTool()
        errors = await tool.validate({"action": "delete"})
        assert len(errors) >= 1
        assert any("event_id" in e for e in errors)

    @pytest.mark.asyncio
    async def test_calendar_execute_list_empty(self) -> None:
        tool = CalendarTool()
        result = await tool.execute({
            "action": "list",
            "calendar_path": "/tmp/nonexistent_calendar_test.ics",
        })
        assert result.success
        assert result.data is not None
        assert result.data["events"] == []
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_calendar_execute_list_with_events(self) -> None:
        ics_content = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Test//Test//CN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:event-001\r\n"
            "DTSTART:20260101T090000\r\n"
            "DTEND:20260101T100000\r\n"
            "SUMMARY:Test Event\r\n"
            "DESCRIPTION:A test event description\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ics", delete=False,
        ) as f:
            f.write(ics_content)
            temp_path = f.name
        try:
            tool = CalendarTool()
            result = await tool.execute({
                "action": "list",
                "calendar_path": temp_path,
            })
            assert result.success
            assert result.data is not None
            assert result.data["count"] == 1
            events = result.data["events"]
            assert len(events) == 1
            assert events[0]["uid"] == "event-001"
            assert events[0]["summary"] == "Test Event"
            assert events[0]["dtstart"] == "20260101T090000"
            assert events[0]["dtend"] == "20260101T100000"
        finally:
            Path(temp_path).unlink(missing_ok=True)
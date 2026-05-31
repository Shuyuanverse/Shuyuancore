from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

try:
    import icalendar

    _HAS_ICALENDAR = True
except ImportError:
    _HAS_ICALENDAR = False

_DEFAULT_CALENDAR = "data/calendar.ics"


class CalendarTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="calendar",
            description="Calendar tool for managing .ics calendar files. "
            "Supports listing, adding, and deleting events.",
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Operation: list / add / delete",
                    required=True,
                ),
                ToolParameter(
                    name="calendar_path",
                    type="string",
                    description="Path to the .ics calendar file",
                    required=False,
                    default=_DEFAULT_CALENDAR,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Event title, required for add",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="start_time",
                    type="string",
                    description="Event start time in ISO format, required for add",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="end_time",
                    type="string",
                    description="Event end time in ISO format, required for add",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Event description",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="event_id",
                    type="string",
                    description="Event UID, required for delete",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "")
        valid_actions = {"list", "add", "delete"}
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors
        if action == "add":
            if not params.get("title"):
                errors.append("add operation requires title parameter")
            if not params.get("start_time"):
                errors.append("add operation requires start_time parameter")
            if not params.get("end_time"):
                errors.append("add operation requires end_time parameter")
        if action == "delete":
            if not params.get("event_id"):
                errors.append("delete operation requires event_id parameter")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        cal_path_str: str = params.get("calendar_path", _DEFAULT_CALENDAR)
        cal_path = Path(cal_path_str)

        if action == "list":
            return await self._list_events(
                cal_path,
                user_id,
                start,
                audit,
            )
        elif action == "add":
            return await self._add_event(
                cal_path,
                params,
                user_id,
                start,
                audit,
            )
        else:
            return await self._delete_event(
                cal_path,
                params,
                user_id,
                start,
                audit,
            )

    async def _list_events(
        self,
        cal_path: Path,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        if not cal_path.exists():
            return ToolResult(
                success=True,
                data={"events": [], "count": 0, "calendar": str(cal_path)},
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            content = cal_path.read_text(encoding="utf-8")
            events = self._parse_ics_events(content)

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.list",
                resource=str(cal_path),
                params={},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "events": events,
                    "count": len(events),
                    "calendar": str(cal_path),
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.list",
                resource=str(cal_path),
                params={},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to list events: {e}",
                duration_ms=duration_ms,
            )

    async def _add_event(
        self,
        cal_path: Path,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        title: str = params["title"]
        start_time: str = params["start_time"]
        end_time: str = params["end_time"]
        description: str = params.get("description", "")
        event_id: str = str(uuid.uuid4())

        try:
            existing_events: list[dict[str, str]] = []
            if cal_path.exists():
                content = cal_path.read_text(encoding="utf-8")
                existing_events = self._parse_ics_events(content)

            new_event = {
                "uid": event_id,
                "dtstart": start_time,
                "dtend": end_time,
                "summary": title,
                "description": description,
            }
            existing_events.append(new_event)

            ics_content = self._build_ics(existing_events)
            cal_path.parent.mkdir(parents=True, exist_ok=True)
            cal_path.write_text(ics_content, encoding="utf-8")

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.add",
                resource=str(cal_path),
                params={
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "event_id": event_id,
                },
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "event_id": event_id,
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.add",
                resource=str(cal_path),
                params={"title": title},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to add event: {e}",
                duration_ms=duration_ms,
            )

    async def _delete_event(
        self,
        cal_path: Path,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        if not cal_path.exists():
            return ToolResult(
                success=False,
                error=f"Calendar file not found: {cal_path}",
                duration_ms=(time.time() - start) * 1000,
            )

        approval_mgr = await get_approval_manager()
        req = await approval_mgr.request(
            tool_name="calendar",
            params=params,
            user_id=user_id,
            timeout=300,
        )
        approved = await approval_mgr.wait(req.approval_id, timeout=300)
        if not approved:
            audit.log(
                user_id=user_id,
                action="calendar.delete",
                resource=str(cal_path),
                params={"event_id": params.get("event_id")},
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error="Calendar delete was not approved",
                duration_ms=(time.time() - start) * 1000,
                approval_id=req.approval_id,
            )

        event_id: str = params["event_id"]

        try:
            content = cal_path.read_text(encoding="utf-8")
            events = self._parse_ics_events(content)
            filtered = [e for e in events if e.get("uid") != event_id]

            if len(filtered) == len(events):
                return ToolResult(
                    success=False,
                    error=f"Event {event_id} not found",
                    duration_ms=(time.time() - start) * 1000,
                )

            ics_content = self._build_ics(filtered)
            cal_path.write_text(ics_content, encoding="utf-8")

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.delete",
                resource=str(cal_path),
                params={"event_id": event_id},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"event_id": event_id, "deleted": True},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="calendar.delete",
                resource=str(cal_path),
                params={"event_id": event_id},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Failed to delete event: {e}",
                duration_ms=duration_ms,
            )

    def _parse_ics_events(self, content: str) -> list[dict[str, str]]:
        if _HAS_ICALENDAR:
            return self._parse_ics_with_icalendar(content)
        return self._parse_ics_manually(content)

    def _parse_ics_with_icalendar(
        self,
        content: str,
    ) -> list[dict[str, str]]:
        cal = icalendar.Calendar.from_ical(content)
        events: list[dict[str, str]] = []
        for component in cal.walk():
            if component.name == "VEVENT":
                uid = str(component.get("UID", ""))
                dtstart = component.get("DTSTART")
                dtend = component.get("DTEND")
                events.append(
                    {
                        "uid": uid,
                        "summary": str(component.get("SUMMARY", "")),
                        "description": str(component.get("DESCRIPTION", "")),
                        "dtstart": self._format_dt(dtstart),
                        "dtend": self._format_dt(dtend),
                    }
                )
        return events

    def _parse_ics_manually(self, content: str) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        current: dict[str, str] = {}
        in_event = False

        for line in content.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                in_event = True
                current = {}
            elif line == "END:VEVENT":
                in_event = False
                if current:
                    events.append(current)
                current = {}
            elif in_event and ":" in line:
                key, _, value = line.partition(":")
                if key == "UID":
                    current["uid"] = value
                elif key == "SUMMARY":
                    current["summary"] = value
                elif key == "DESCRIPTION":
                    current["description"] = value
                elif key == "DTSTART":
                    current["dtstart"] = value
                elif key == "DTEND":
                    current["dtend"] = value

        return events

    def _build_ics(self, events: list[dict[str, str]]) -> str:
        now = datetime.now(timezone.utc)
        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ShuyuanCore//CalendarTool//CN",
        ]

        for event in events:
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{event.get('uid', str(uuid.uuid4()))}")
            lines.append(f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}")
            dtstart = event.get("dtstart", "")
            if dtstart:
                dtstart_ics = self._to_ics_dt(dtstart)
                lines.append(f"DTSTART:{dtstart_ics}")
            dtend = event.get("dtend", "")
            if dtend:
                dtend_ics = self._to_ics_dt(dtend)
                lines.append(f"DTEND:{dtend_ics}")
            summary = event.get("summary", "")
            if summary:
                lines.append(f"SUMMARY:{summary}")
            description = event.get("description", "")
            if description:
                lines.append(f"DESCRIPTION:{description}")
            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    @staticmethod
    def _format_dt(dt_value: Any) -> str:
        if hasattr(dt_value, "strftime"):
            return dt_value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(dt_value)

    @staticmethod
    def _to_ics_dt(iso_str: str) -> str:
        cleaned = iso_str.replace("-", "").replace(":", "")
        cleaned = cleaned.replace("T", "T")
        if "T" in cleaned:
            parts = cleaned.split("T")
            if len(parts[0]) == 8 and len(parts[1]) >= 6:
                return parts[0] + "T" + parts[1][:6]
        if len(cleaned) >= 8:
            return cleaned[:8] + "T" + cleaned[8:14] if len(cleaned) > 8 else cleaned[:8]
        return cleaned

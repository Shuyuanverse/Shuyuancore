from __future__ import annotations

import base64
import json
from typing import Any


def encode_cursor(timestamp: int, entity_id: str) -> str:
    raw = f"{timestamp}_{entity_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sep = raw.index("_")
        timestamp = int(raw[:sep])
        entity_id = raw[sep + 1 :]
        return timestamp, entity_id
    except (ValueError, base64.binascii.Error):
        return None


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def error_response(code: int, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets as _secrets
import time as _time
from typing import Any

logger = logging.getLogger(__name__)

_CURSOR_SECRET: str | None = None


def set_cursor_secret(secret: str) -> None:
    global _CURSOR_SECRET
    _CURSOR_SECRET = secret


def get_cursor_secret() -> str:
    global _CURSOR_SECRET
    if _CURSOR_SECRET is None:
        _CURSOR_SECRET = _secrets.token_urlsafe(32)
        logger.warning(
            "Cursor secret not configured, using random value for this session. "
            "Set CURSOR_SECRET env var or security.cursor_secret in config for persistence."
        )
    return _CURSOR_SECRET


def encode_cursor(timestamp: int, entity_id: str, expires_in: int = 3600) -> str:
    secret = get_cursor_secret()
    expires_at = int(_time.time()) + expires_in
    safe_id = base64.urlsafe_b64encode(entity_id.encode()).decode()
    data = f"{timestamp}_{safe_id}_{expires_at}"
    sig = hmac.new(
        secret.encode(), data.encode(), hashlib.sha256
    ).hexdigest()[:16]
    combined = f"{data}_{sig}"
    return base64.urlsafe_b64encode(combined.encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, str] | None:
    try:
        secret = get_cursor_secret()
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()

        parts = raw.rsplit("_", 1)
        if len(parts) != 2:
            return None
        data, sig = parts

        expected = hmac.new(
            secret.encode(), data.encode(), hashlib.sha256
        ).hexdigest()[:16]
        if not hmac.compare_digest(expected, sig):
            return None

        data_parts = data.split("_")
        if len(data_parts) != 3:
            return None
        timestamp_str, entity_id_b64, expires_at_str = data_parts
        timestamp = int(timestamp_str)
        expires_at = int(expires_at_str)

        if int(_time.time()) > expires_at:
            return None

        entity_id = base64.urlsafe_b64decode(entity_id_b64.encode()).decode()
        return timestamp, entity_id
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def error_response(code: int, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body

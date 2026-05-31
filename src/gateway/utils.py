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

from src.security.cursor import (
    decode_cursor,
    encode_cursor,
    get_cursor_secret,
    set_cursor_secret,
)

logger = logging.getLogger(__name__)


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def error_response(code: int, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return body

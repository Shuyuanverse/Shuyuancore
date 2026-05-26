from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    timestamp: float
    user_id: str
    action: str
    resource: str
    params: dict[str, Any]
    result: str
    approved: bool | None
    approval_id: str
    duration_ms: float
    ip_address: str = ""
    error: str = ""


class AuditLogger:
    _entries: list[AuditEntry]

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    _max_entries: int = 10000

    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        params: dict[str, Any],
        result: str = "success",
        approved: bool | None = None,
        approval_id: str = "",
        duration_ms: float = 0.0,
        ip_address: str = "",
        error: str = "",
    ) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            resource=resource,
            params=_sanitize_params(params),
            result=result,
            approved=approved,
            approval_id=approval_id,
            duration_ms=duration_ms,
            ip_address=ip_address,
            error=error,
        )
        self._entries.append(entry)
        logger.info(
            "audit: %s %s on %s -> %s (%.1fms)",
            user_id,
            action,
            resource,
            result,
            duration_ms,
        )
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]

    def get_entries(
        self,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        entries = self._entries
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if action:
            entries = [e for e in entries if e.action == action]
        return [asdict(e) for e in entries[-limit:]]


_SENSITIVE_KEYS = {"api_key", "token", "password", "secret", "cookie", "authorization"}


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_params(value)
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:200] + "...[truncated]"
        else:
            sanitized[key] = value
    return sanitized


_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    return _audit_logger
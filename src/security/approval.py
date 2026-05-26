from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_name: str
    params: dict[str, Any]
    user_id: str
    created_at: float
    timeout: int
    status: str = "pending"
    approved: bool | None = None
    reason: str = ""
    resolved_by: str = ""
    resolved_at: float = 0.0
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class ApprovalManager:
    _requests: dict[str, ApprovalRequest] = {}
    _counter: int = 0

    async def request(
        self,
        tool_name: str,
        params: dict[str, Any],
        user_id: str,
        timeout: int = 300,
        approval_id: str | None = None,
    ) -> ApprovalRequest:
        self._counter += 1
        if approval_id is None:
            approval_id = f"apr_{int(time.time())}_{self._counter}"
        req = ApprovalRequest(
            approval_id=approval_id,
            tool_name=tool_name,
            params=params,
            user_id=user_id,
            created_at=time.time(),
            timeout=timeout,
        )
        self._requests[approval_id] = req
        return req

    async def resolve(
        self,
        approval_id: str,
        approved: bool,
        reason: str = "",
        resolved_by: str = "user",
    ) -> ApprovalRequest:
        req = self._requests.get(approval_id)
        if not req:
            raise ValueError(f"Approval {approval_id} not found")
        req.status = "approved" if approved else "denied"
        req.approved = approved
        req.reason = reason
        req.resolved_by = resolved_by
        req.resolved_at = time.time()
        req._event.set()
        return req

    async def wait(self, approval_id: str, timeout: int = 300) -> bool:
        req = self._requests.get(approval_id)
        if not req:
            raise ValueError(f"Approval {approval_id} not found")
        try:
            await asyncio.wait_for(req._event.wait(), timeout=timeout)
            return req.approved is True
        except asyncio.TimeoutError:
            req.status = "timeout"
            req.approved = False
            req.reason = "审批超时自动拒绝 / Approval timeout auto-denied"
            req.resolved_at = time.time()
            return False

    def get_request(self, approval_id: str) -> ApprovalRequest | None:
        return self._requests.get(approval_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [
            req for req in self._requests.values() if req.status == "pending"
        ]

    def cleanup(self, max_age: int = 86400) -> int:
        now = time.time()
        expired = [
            aid
            for aid, req in self._requests.items()
            if now - req.created_at > max_age
        ]
        for aid in expired:
            self._requests.pop(aid, None)
        return len(expired)


_approval_manager = ApprovalManager()


def get_approval_manager() -> ApprovalManager:
    return _approval_manager

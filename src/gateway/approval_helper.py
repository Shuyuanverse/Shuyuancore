from __future__ import annotations

import uuid

from src.security.approval import ApprovalRequest, get_approval_manager


async def create_approval(
    tool_name: str,
    command: str,
    user_id: str = "default",
    timeout: int = 300,
) -> ApprovalRequest:
    mgr = get_approval_manager()
    approval_id = f"apr_{uuid.uuid4().hex[:8]}_{user_id[:8]}"
    req = await mgr.request(
        tool_name=tool_name,
        params={"command": command},
        user_id=user_id,
        timeout=timeout,
        approval_id=approval_id,
    )
    return req


async def resolve_approval(
    approval_id: str,
    approved: bool,
    reason: str = "",
) -> ApprovalRequest:
    mgr = get_approval_manager()
    return await mgr.resolve(
        approval_id=approval_id,
        approved=approved,
        reason=reason,
    )


def get_pending_approvals() -> list[ApprovalRequest]:
    mgr = get_approval_manager()
    return mgr.list_pending()


def get_approval(approval_id: str) -> ApprovalRequest | None:
    mgr = get_approval_manager()
    return mgr.get_request(approval_id)

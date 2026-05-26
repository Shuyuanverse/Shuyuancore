from __future__ import annotations

import uuid

from src.security.approval import (
    ApprovalRequest,
    get_approval_manager,
)


async def create_approval(
    tool_name: str,
    command: str,
    user_id: str = "default",
    timeout: int = 300,
) -> ApprovalRequest:
    mgr = await get_approval_manager()
    approval_id = f"{user_id}_{uuid.uuid4().hex[:12]}"
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
    mgr = await get_approval_manager()
    return await mgr.resolve(
        approval_id=approval_id,
        approved=approved,
        reason=reason,
    )


async def get_pending_approvals_by_user(user_id: str) -> list[ApprovalRequest]:
    mgr = await get_approval_manager()
    return await mgr.list_pending_by_user(user_id)


async def get_approval(approval_id: str) -> ApprovalRequest | None:
    mgr = await get_approval_manager()
    return await mgr.aget_request(approval_id)

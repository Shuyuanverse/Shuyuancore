from __future__ import annotations

from src.config import get_settings
from src.security.approval import ApprovalRequest, get_approval_manager


async def request_approval(
    tool_name: str,
    params: dict,
    user_id: str = "default",
) -> ApprovalRequest:
    config = get_settings().tools
    mgr = await get_approval_manager()
    return await mgr.request(
        tool_name=tool_name,
        params=params,
        user_id=user_id,
        timeout=config.approval_timeout,
    )


async def wait_for_approval(approval_id: str) -> bool:
    config = get_settings().tools
    mgr = await get_approval_manager()
    return await mgr.wait(approval_id, timeout=config.approval_timeout)


async def get_pending_approvals() -> list[ApprovalRequest]:
    mgr = await get_approval_manager()
    return await mgr.list_pending_by_user("default")

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 需要二次确认的敏感操作列表 / Sensitive operations requiring confirmation
SENSITIVE_OPERATIONS: frozenset[str] = frozenset(
    {
        "file_delete",
        "code_exec",
        "data_export",
        "config_change",
        "system_command",
    }
)


@dataclass
class ConfirmRequest:
    """二次确认请求 / Confirmation request

    Attributes:
        id: 唯一标识符
        user_id: 用户 ID
        action: 操作名称
        params: 操作参数
        timeout: 超时时间（秒）
        status: 状态（pending/approved/denied/cancelled/expired）
        confirmed_at: 确认时间
        reason: 确认理由
    """
    id: str
    user_id: str
    action: str
    params: dict[str, Any]
    timeout: int
    status: str = "pending"
    confirmed_at: float = 0.0
    reason: str = ""
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class ConfirmationManager:
    """二次确认管理器 / Confirmation manager

    管理敏感操作的二次确认流程，使用内存存储和 asyncio.Event 实现同步。
    """

    def __init__(self) -> None:
        self._requests: dict[str, ConfirmRequest] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def request_confirmation(
        self,
        user_id: str,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> ConfirmRequest:
        """创建二次确认请求 / Create a confirmation request

        Args:
            user_id: 发起请求的用户 ID
            action: 需要确认的操作名称
            params: 操作参数
            timeout: 超时时间（秒），默认 60 秒

        Returns:
            创建的 ConfirmRequest 对象

        Raises:
            ValueError: 如果操作不在敏感操作列表中
        """
        if action not in SENSITIVE_OPERATIONS:
            raise ValueError(
                f"操作 '{action}' 不在敏感操作列表中 / "
                f"Action '{action}' is not in sensitive operations list"
            )

        confirm_id = f"confirm_{uuid.uuid4().hex[:16]}"
        request = ConfirmRequest(
            id=confirm_id,
            user_id=user_id,
            action=action,
            params=params or {},
            timeout=timeout,
        )

        async with self._lock:
            self._requests[confirm_id] = request

        logger.info(
            "二次确认请求已创建: %s 操作=%s / Confirmation request created: %s action=%s",
            confirm_id,
            action,
            confirm_id,
            action,
        )
        return request

    async def confirm(
        self, confirm_id: str, approved: bool, reason: str = ""
    ) -> ConfirmRequest:
        """确认或拒绝操作 / Approve or deny a confirmation request

        Args:
            confirm_id: 确认请求 ID
            approved: 是否批准
            reason: 确认理由

        Returns:
            更新后的 ConfirmRequest 对象

        Raises:
            ValueError: 如果请求不存在或已过期
        """
        async with self._lock:
            request = self._requests.get(confirm_id)
            if request is None:
                raise ValueError(
                    f"确认请求不存在: {confirm_id} / Confirmation request not found: {confirm_id}"
                )
            if request.status != "pending":
                raise ValueError(
                    f"确认请求已处理: {confirm_id} / Confirmation request already processed: {confirm_id}"
                )

            now = time.time()
            if now - (request.confirmed_at or now) > request.timeout:
                request.status = "expired"
                raise ValueError(
                    f"确认请求已过期: {confirm_id} / Confirmation request expired: {confirm_id}"
                )

            request.status = "approved" if approved else "denied"
            request.confirmed_at = now
            request.reason = reason
            request._event.set()

        status_text = "已批准" if approved else "已拒绝"
        logger.info(
            "二次确认 %s: %s / Confirmation %s: %s",
            status_text,
            confirm_id,
            status_text,
            confirm_id,
        )
        return request

    async def get_pending(self, user_id: str) -> list[ConfirmRequest]:
        """获取用户待处理的确认请求 / Get pending confirmation requests for a user

        Args:
            user_id: 用户 ID

        Returns:
            待处理的确认请求列表
        """
        async with self._lock:
            now = time.time()
            results: list[ConfirmRequest] = []
            expired: list[str] = []
            for req_id, req in self._requests.items():
                if req.user_id != user_id:
                    continue
                if req.status != "pending":
                    continue
                if now - req.confirmed_at > req.timeout:
                    expired.append(req_id)
                    continue
                results.append(req)
            for req_id in expired:
                self._requests[req_id].status = "expired"
        return results

    async def cancel(self, confirm_id: str) -> None:
        """取消确认请求 / Cancel a confirmation request

        Args:
            confirm_id: 要取消的确认请求 ID

        Raises:
            ValueError: 如果请求不存在
        """
        async with self._lock:
            request = self._requests.get(confirm_id)
            if request is None:
                raise ValueError(
                    f"确认请求不存在: {confirm_id} / Confirmation request not found: {confirm_id}"
                )
            if request.status != "pending":
                raise ValueError(
                    f"确认请求已处理，无法取消: {confirm_id} / "
                    f"Confirmation request already processed, cannot cancel: {confirm_id}"
                )
            request.status = "cancelled"
            request._event.set()

        logger.info(
            "确认请求已取消: %s / Confirmation request cancelled: %s",
            confirm_id,
            confirm_id,
        )

    async def wait(self, confirm_id: str, timeout: int | None = None) -> bool:
        """等待确认结果 / Wait for confirmation result

        Args:
            confirm_id: 确认请求 ID
            timeout: 等待超时（秒），默认使用请求的超时时间

        Returns:
            是否被批准

        Raises:
            ValueError: 如果请求不存在
        """
        async with self._lock:
            request = self._requests.get(confirm_id)
            if request is None:
                raise ValueError(
                    f"确认请求不存在: {confirm_id} / Confirmation request not found: {confirm_id}"
                )
            event = request._event
            wait_timeout = timeout if timeout is not None else request.timeout

        try:
            await asyncio.wait_for(event.wait(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            async with self._lock:
                if confirm_id in self._requests:
                    self._requests[confirm_id].status = "expired"
            return False

        async with self._lock:
            req = self._requests.get(confirm_id)
            if req is None:
                return False
            return req.status == "approved"

    async def cleanup(self, max_age: int = 86400) -> int:
        """清理过期请求 / Clean up expired requests

        Args:
            max_age: 最大存活时间（秒），默认 86400（1天）

        Returns:
            清理的请求数量
        """
        now = time.time()
        threshold = now - max_age
        removed = 0

        async with self._lock:
            expired_ids = [
                req_id
                for req_id, req in self._requests.items()
                if req.confirmed_at > 0 and req.confirmed_at < threshold
            ]
            for req_id in expired_ids:
                del self._requests[req_id]
                removed += 1

        if removed > 0:
            logger.info(
                "已清理 %d 个过期确认请求 / Cleaned up %d expired confirmation requests",
                removed,
                removed,
            )
        return removed


_manager: ConfirmationManager | None = None
_manager_lock: asyncio.Lock = asyncio.Lock()


async def get_confirmation_manager() -> ConfirmationManager:
    """获取 ConfirmationManager 单例 / Get ConfirmationManager singleton"""
    global _manager
    if _manager is None:
        async with _manager_lock:
            if _manager is None:
                _manager = ConfirmationManager()
    return _manager
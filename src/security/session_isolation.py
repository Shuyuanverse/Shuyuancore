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


@dataclass
class Session:
    """会话数据模型 / Session data model

    Attributes:
        session_id: 会话唯一标识
        user_id: 所属用户 ID
        created_at: 创建时间戳
        last_active: 最后活跃时间戳
        data: 会话数据
        is_expired: 是否已过期
        metadata: 额外元数据
    """
    session_id: str
    user_id: str
    created_at: float
    last_active: float
    data: dict[str, Any] = field(default_factory=dict)
    is_expired: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionIsolator:
    """会话隔离器 / Session isolator

    管理用户会话的创建、验证和生命周期，确保会话级数据隔离。
    使用内存存储和 asyncio.Lock 保证线程安全。
    """

    def __init__(self, session_ttl: int = 3600, cleanup_interval: int = 300) -> None:
        self._session_ttl: int = session_ttl
        self._cleanup_interval: int = cleanup_interval
        self._sessions: dict[str, Session] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动后台清理任务 / Start background cleanup task"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """停止后台清理任务 / Stop background cleanup task"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def create_session(self, user_id: str) -> Session:
        """创建新会话 / Create a new session

        Args:
            user_id: 用户 ID

        Returns:
            创建的 Session 对象
        """
        now = time.time()
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_active=now,
        )

        async with self._lock:
            self._sessions[session_id] = session

        logger.info(
            "会话已创建: %s 用户=%s / Session created: %s user=%s",
            session_id,
            user_id,
            session_id,
            user_id,
        )
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """获取会话 / Get a session by ID

        Args:
            session_id: 会话 ID

        Returns:
            Session 对象或 None
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                session.is_expired = True
                return session
            session.last_active = time.time()
            return session

    async def validate_session(self, session_id: str) -> bool:
        """验证会话是否有效 / Validate if a session is still valid

        Args:
            session_id: 会话 ID

        Returns:
            True 如果会话有效
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            if self._is_expired(session):
                session.is_expired = True
                return False
            session.last_active = time.time()
            return True

    async def update_session(self, session_id: str, data: dict[str, Any]) -> None:
        """更新会话数据 / Update session data

        Args:
            session_id: 会话 ID
            data: 要更新的数据

        Raises:
            ValueError: 如果会话不存在
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(
                    f"会话不存在: {session_id} / Session not found: {session_id}"
                )
            session.data.update(data)
            session.last_active = time.time()

    async def delete_session(self, session_id: str) -> None:
        """删除会话 / Delete a session

        Args:
            session_id: 要删除的会话 ID
        """
        async with self._lock:
            self._sessions.pop(session_id, None)

        logger.info(
            "会话已删除: %s / Session deleted: %s",
            session_id,
            session_id,
        )

    async def get_user_sessions(self, user_id: str) -> list[Session]:
        """获取用户的所有活跃会话 / Get all active sessions for a user

        Args:
            user_id: 用户 ID

        Returns:
            活跃会话列表
        """
        async with self._lock:
            now = time.time()
            results: list[Session] = []
            expired_ids: list[str] = []
            for session_id, session in self._sessions.items():
                if session.user_id != user_id:
                    continue
                if self._is_expired(session):
                    expired_ids.append(session_id)
                    continue
                results.append(session)
            for sid in expired_ids:
                self._sessions[sid].is_expired = True
            return results

    def is_expired(self, session: Session) -> bool:
        """检查会话是否过期 / Check if a session is expired

        Args:
            session: 要检查的会话

        Returns:
            True 如果已过期
        """
        return self._is_expired(session)

    def _is_expired(self, session: Session) -> bool:
        """内部过期检查 / Internal expiration check

        Args:
            session: 要检查的会话

        Returns:
            True 如果已过期
        """
        if session.is_expired:
            return True
        elapsed = time.time() - session.last_active
        return elapsed > self._session_ttl

    async def _cleanup_expired(self) -> int:
        """清理过期会话 / Clean up expired sessions

        Returns:
            清理的会话数量
        """
        now = time.time()
        async with self._lock:
            expired_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if self._is_expired(session)
            ]
            for sid in expired_ids:
                del self._sessions[sid]

        if expired_ids:
            logger.info(
                "已清理 %d 个过期会话 / Cleaned up %d expired sessions",
                len(expired_ids),
                len(expired_ids),
            )
        return len(expired_ids)

    async def _cleanup_loop(self) -> None:
        """后台清理循环 / Background cleanup loop"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("会话清理异常 / Session cleanup error")


_isolator: SessionIsolator | None = None
_isolator_lock: asyncio.Lock = asyncio.Lock()


async def get_session_isolator(
    session_ttl: int = 3600,
    cleanup_interval: int = 300,
) -> SessionIsolator:
    """获取 SessionIsolator 单例 / Get SessionIsolator singleton

    Args:
        session_ttl: 会话 TTL（秒），默认 3600（1小时）
        cleanup_interval: 清理间隔（秒），默认 300（5分钟）

    Returns:
        SessionIsolator 实例
    """
    global _isolator
    if _isolator is None:
        async with _isolator_lock:
            if _isolator is None:
                _isolator = SessionIsolator(
                    session_ttl=session_ttl,
                    cleanup_interval=cleanup_interval,
                )
                await _isolator.start()
    return _isolator
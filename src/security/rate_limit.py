# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """速率限制规则 / Rate limit rule

    Attributes:
        path: 匹配的路径模式
        limit: 允许的最大请求数
        window: 时间窗口（秒）
    """
    path: str
    limit: int
    window: int = 60


@dataclass
class _TokenBucket:
    """令牌桶 / Token bucket

    Attributes:
        tokens: 当前可用令牌数
        capacity: 桶容量
        fill_rate: 填充速率（令牌/秒）
        last_refill: 上次填充时间戳
        window_start: 当前窗口开始时间
    """
    tokens: float
    capacity: float
    fill_rate: float
    last_refill: float
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """速率限制器 / Rate limiter

    使用令牌桶算法实现速率限制，支持自定义规则和用户级配额。
    """

    def __init__(self, default_rpm: int = 60) -> None:
        self._default_rpm: int = default_rpm
        self._buckets: dict[str, _TokenBucket] = {}
        self._rules: list[RateLimitRule] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    async def check(self, key: str, cost: int = 1) -> bool:
        """检查是否允许请求 / Check if a request is allowed

        使用令牌桶算法，每次请求消耗指定数量的令牌。

        Args:
            key: 限流键（可以是用户 ID、IP 等）
            cost: 消耗的令牌数，默认 1

        Returns:
            True 如果允许请求
        """
        async with self._lock:
            now = time.time()
            bucket = self._buckets.get(key)
            if bucket is None:
                capacity = float(self._default_rpm)
                bucket = _TokenBucket(
                    tokens=capacity,
                    capacity=capacity,
                    fill_rate=capacity / 60.0,
                    last_refill=now,
                )
                self._buckets[key] = bucket

            # 检查自定义规则
            for rule in self._rules:
                if self._match_rule(key, rule):
                    bucket.capacity = float(rule.limit)
                    bucket.fill_rate = rule.limit / rule.window
                    break

            # 补充令牌
            elapsed = now - bucket.last_refill
            bucket.tokens = min(
                bucket.capacity,
                bucket.tokens + elapsed * bucket.fill_rate,
            )
            bucket.last_refill = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            return False

    def get_remaining(self, key: str) -> int:
        """获取剩余可用配额 / Get remaining quota for a key

        Args:
            key: 限流键

        Returns:
            剩余可用请求数
        """
        bucket = self._buckets.get(key)
        if bucket is None:
            return self._default_rpm
        now = time.time()
        elapsed = now - bucket.last_refill
        tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.fill_rate)
        return int(tokens)

    def get_reset_time(self, key: str) -> float:
        """获取配额重置的剩余时间 / Get remaining time until quota reset

        Args:
            key: 限流键

        Returns:
            距离重置的剩余秒数
        """
        bucket = self._buckets.get(key)
        if bucket is None:
            return 0.0
        now = time.time()
        if bucket.tokens >= bucket.capacity:
            return 0.0
        tokens_needed = bucket.capacity - bucket.tokens
        if bucket.fill_rate <= 0:
            return float("inf")
        reset_seconds = tokens_needed / bucket.fill_rate
        return max(0.0, reset_seconds)

    def add_rule(self, rule: RateLimitRule) -> None:
        """添加自定义限流规则 / Add a custom rate limit rule

        Args:
            rule: 速率限制规则
        """
        self._rules.append(rule)
        logger.info(
            "限流规则已添加: %s -> %d/min / Rate limit rule added: %s -> %d/min",
            rule.path,
            rule.limit,
            rule.path,
            rule.limit,
        )

    def get_user_limits(self, user_id: str) -> dict[str, Any]:
        """获取用户限流状态 / Get rate limit status for a user

        Args:
            user_id: 用户 ID

        Returns:
            包含限流状态信息的字典
        """
        remaining = self.get_remaining(user_id)
        reset_time = self.get_reset_time(user_id)
        bucket = self._buckets.get(user_id)
        return {
            "user_id": user_id,
            "remaining": remaining,
            "reset_time_seconds": reset_time,
            "limit": int(bucket.capacity) if bucket else self._default_rpm,
            "is_limited": remaining <= 0,
        }

    def _match_rule(self, key: str, rule: RateLimitRule) -> bool:
        """检查键是否匹配规则 / Check if a key matches a rule

        Args:
            key: 要检查的键
            rule: 限流规则

        Returns:
            True 如果匹配
        """
        return rule.path in key


_limiter: RateLimiter | None = None
_limiter_lock: asyncio.Lock = asyncio.Lock()


async def get_rate_limiter(default_rpm: int = 60) -> RateLimiter:
    """获取 RateLimiter 单例 / Get RateLimiter singleton

    Args:
        default_rpm: 默认每分钟允许的请求数

    Returns:
        RateLimiter 实例
    """
    global _limiter
    if _limiter is None:
        async with _limiter_lock:
            if _limiter is None:
                _limiter = RateLimiter(default_rpm=default_rpm)
    return _limiter
# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import abc
import hashlib
import hmac
import logging
import secrets
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """认证失败异常 / Authentication failure exception"""


class AuthorizationError(Exception):
    """授权失败异常 / Authorization failure exception"""


class InvalidTokenError(AuthenticationError):
    """无效 Token 异常 / Invalid token exception"""


class AuthProvider(abc.ABC):
    """认证提供者抽象基类 / Abstract base class for authentication providers"""

    @abc.abstractmethod
    def authenticate(self, token: str) -> dict[str, Any] | None:
        """验证 token 并返回用户信息 / Authenticate token and return user info"""

    @abc.abstractmethod
    def validate_permission(
        self, user_info: dict[str, Any], required_permission: str
    ) -> bool:
        """校验用户权限 / Validate user permission"""


class _AuthCache:
    """认证结果缓存（5分钟 TTL）/ Authentication result cache with 5-minute TTL"""

    def __init__(self, ttl: int = 300) -> None:
        self._ttl: int = ttl
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: dict[str, Any] | None) -> None:
        self._cache[key] = (time.time() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


class ApiKeyAuthProvider(AuthProvider):
    """基于 API Key 的认证提供者 / API Key based authentication provider

    从配置加载 API Key 列表，支持创建、验证、吊销 token 以及权限校验。
    """

    def __init__(self, api_keys: list[dict[str, str]] | None = None) -> None:
        self._keys: dict[str, dict[str, Any]] = {}
        self._cache = _AuthCache()
        if api_keys:
            for entry in api_keys:
                key = entry.get("key", "")
                if key:
                    self._keys[key] = {
                        "user_id": entry.get("user_id", ""),
                        "role": entry.get("role", "user"),
                        "permissions": entry.get("permissions", "").split(",")
                        if entry.get("permissions")
                        else [],
                    }

    def authenticate(self, token: str) -> dict[str, Any] | None:
        """验证 API Key，返回用户信息 / Authenticate API key and return user info

        Args:
            token: 待验证的 API Key / API key to authenticate

        Returns:
            用户信息字典或 None / User info dict or None
        """
        cached = self._cache.get(token)
        if cached is not None:
            return cached

        entry = self._keys.get(token)
        if entry is None:
            return None

        user_info: dict[str, Any] = {
            "user_id": entry["user_id"],
            "role": entry["role"],
            "permissions": list(entry["permissions"]),
            "token_type": "api_key",
        }
        self._cache.set(token, user_info)
        return user_info

    def create_token(
        self,
        user_id: str,
        role: str = "user",
        permissions: list[str] | None = None,
    ) -> str:
        """生成新的 API Key / Generate a new API key

        Args:
            user_id: 用户 ID
            role: 角色
            permissions: 权限列表

        Returns:
            生成的 API Key / Generated API key
        """
        raw = f"{user_id}:{role}:{uuid.uuid4().hex}:{secrets.token_hex(16)}"
        token = f"sk-{hashlib.sha256(raw.encode()).hexdigest()[:48]}"
        self._keys[token] = {
            "user_id": user_id,
            "role": role,
            "permissions": list(permissions or []),
        }
        logger.info("已为 %s 生成新 API Key / New API key created for %s", user_id, user_id)
        return token

    def revoke_token(self, token: str) -> None:
        """吊销指定的 API Key / Revoke an API key

        Args:
            token: 要吊销的 API Key / API key to revoke
        """
        self._keys.pop(token, None)
        self._cache.invalidate(token)
        logger.info("API Key 已吊销 / API key revoked: %s...", token[:12])

    def validate_permission(
        self, user_info: dict[str, Any], required_permission: str
    ) -> bool:
        """校验用户是否拥有指定权限 / Check if user has the required permission

        Args:
            user_info: 用户信息字典
            required_permission: 需要的权限

        Returns:
            是否拥有权限 / Whether the user has the permission
        """
        permissions = user_info.get("permissions", [])
        role = user_info.get("role", "")
        if role == "admin":
            return True
        if required_permission in permissions:
            return True
        logger.warning(
            "权限不足: %s 需要 %s / Permission denied: %s requires %s",
            user_info.get("user_id"),
            required_permission,
            user_info.get("user_id"),
            required_permission,
        )
        return False


class SimpleAuthProvider(AuthProvider):
    """基于配置的简单认证提供者 / Simple configuration-based authentication provider

    从 SecurityConfig.api_keys 加载，通过 Bearer token 进行认证。
    """

    def __init__(self, api_keys: list[dict[str, str]] | None = None) -> None:
        self._valid_tokens: dict[str, str] = {}
        self._cache = _AuthCache()
        if api_keys:
            for entry in api_keys:
                key = entry.get("key", "")
                uid = entry.get("user_id", "")
                if key and uid:
                    self._valid_tokens[key] = uid

    def authenticate(self, token: str) -> dict[str, Any] | None:
        """验证 Bearer token / Authenticate Bearer token

        支持 "Bearer <token>" 格式和纯 token 格式。

        Args:
            token: 待验证的 token

        Returns:
            用户信息字典或 None
        """
        cached = self._cache.get(token)
        if cached is not None:
            return cached

        raw = token
        if token.startswith("Bearer "):
            raw = token[7:]

        user_id = self._valid_tokens.get(raw)
        if user_id is None:
            return None

        user_info: dict[str, Any] = {
            "user_id": user_id,
            "role": "user",
            "permissions": [],
            "token_type": "bearer",
        }
        self._cache.set(token, user_info)
        return user_info

    def get_user_id(self, token: str) -> str | None:
        """从 token 获取用户 ID / Extract user ID from token

        Args:
            token: 认证 token

        Returns:
            用户 ID 或 None
        """
        info = self.authenticate(token)
        if info is None:
            return None
        return info.get("user_id")

    def validate_permission(
        self, user_info: dict[str, Any], required_permission: str
    ) -> bool:
        """简单认证提供者始终返回 True（权限由上层控制） / Always returns True for simple auth

        Args:
            user_info: 用户信息
            required_permission: 需要的权限

        Returns:
            始终返回 True
        """
        return True


_auth_cache: dict[str, AuthProvider] = {}


def get_auth_provider(
    provider_type: str = "api_key",
    api_keys: list[dict[str, str]] | None = None,
) -> AuthProvider:
    """获取认证提供者单例 / Get auth provider singleton

    Args:
        provider_type: 提供者类型 ("api_key" 或 "simple")
        api_keys: API Key 配置列表

    Returns:
        AuthProvider 实例
    """
    if provider_type not in _auth_cache:
        if provider_type == "simple":
            _auth_cache[provider_type] = SimpleAuthProvider(api_keys=api_keys)
        else:
            _auth_cache[provider_type] = ApiKeyAuthProvider(api_keys=api_keys)
    return _auth_cache[provider_type]
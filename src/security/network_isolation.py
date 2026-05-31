# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 默认允许的公共域名白名单 / Default allowed public domains whitelist
_DEFAULT_ALLOWED_DOMAINS: list[str] = [
    "api.openai.com",
    "api.deepseek.com",
    "api.anthropic.com",
    "api.cohere.ai",
    "api.mistral.ai",
    "github.com",
    "raw.githubusercontent.com",
    "pypi.org",
    "pypi.python.org",
    "files.pythonhosted.org",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "registry.npmjs.org",
    "hub.docker.com",
    "docker.io",
    "nginx.org",
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "baidu.com",
    "www.baidu.com",
]

# 常见的私有 IP 段 / Common private IP ranges
_PRIVATE_CIDRS: list[str] = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]


@dataclass
class NetworkIsolationPolicy:
    """网络隔离策略 / Network isolation policy

    Attributes:
        allowed_domains: 允许访问的域名白名单
        blocked_domains: 禁止访问的域名黑名单
        allow_private_ip: 是否允许私有 IP 访问
        allow_localhost: 是否允许本地回环地址
        default_allow: 默认是否允许（未匹配白名单/黑名单时）
    """
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    allow_private_ip: bool = False
    allow_localhost: bool = False
    default_allow: bool = True


class NetworkIsolator:
    """网络隔离器 / Network isolator

    控制和管理网络访问策略，阻止访问内网地址和黑名单域名。
    """

    def __init__(self, policy: NetworkIsolationPolicy | None = None) -> None:
        self._policy: NetworkIsolationPolicy = policy or NetworkIsolationPolicy(
            allowed_domains=list(_DEFAULT_ALLOWED_DOMAINS),
            blocked_domains=[],
            allow_private_ip=False,
            allow_localhost=False,
            default_allow=True,
        )

    def check_url(self, url: str) -> bool:
        """检查 URL 是否允许访问 / Check if a URL is allowed to access

        Args:
            url: 要检查的 URL

        Returns:
            True 如果允许访问
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            scheme = parsed.scheme or ""
        except Exception:
            logger.warning("无法解析 URL: %s / Cannot parse URL: %s", url, url)
            return False

        if not scheme:
            logger.warning("URL 缺少协议: %s / URL missing scheme: %s", url, url)
            return False

        # 只允许 HTTPS（除非策略配置了其他）
        if scheme not in ("https", "http"):
            logger.warning("不支持的协议: %s / Unsupported scheme: %s", scheme, scheme)
            return False

        # 检查黑名单
        if self._is_blocked(hostname):
            logger.warning("域名在黑名单中: %s / Domain is blocked: %s", hostname, hostname)
            return False

        # 检查是否为私有 IP
        if self._is_private_ip(hostname):
            if not self._policy.allow_private_ip:
                logger.warning("私有 IP 被阻止: %s / Private IP blocked: %s", hostname, hostname)
                return False
            if not self._policy.allow_localhost and self._is_localhost(hostname):
                logger.warning("本地地址被阻止: %s / Localhost blocked: %s", hostname, hostname)
                return False
            return True

        # 白名单模式：如果有白名单，只允许白名单中的域名
        if self._policy.allowed_domains:
            if self._is_allowed(hostname):
                return True
            if self._policy.default_allow:
                logger.info("域名不在白名单中但默认允许: %s", hostname)
                return True
            logger.warning("域名不在白名单中: %s / Domain not allowed: %s", hostname, hostname)
            return False

        return self._policy.default_allow

    def add_allowed_domain(self, domain: str) -> None:
        """添加域名到白名单 / Add a domain to the whitelist

        Args:
            domain: 要添加的域名
        """
        normalized = domain.lower().strip()
        if normalized not in self._policy.allowed_domains:
            self._policy.allowed_domains.append(normalized)
            logger.info("域名已加入白名单: %s / Domain whitelisted: %s", domain, domain)

    def block_domain(self, domain: str) -> None:
        """添加域名到黑名单 / Add a domain to the blocklist

        Args:
            domain: 要封禁的域名
        """
        normalized = domain.lower().strip()
        if normalized not in self._policy.blocked_domains:
            self._policy.blocked_domains.append(normalized)
            logger.info("域名已加入黑名单: %s / Domain blocked: %s", domain, domain)

    def get_policy(self) -> NetworkIsolationPolicy:
        """获取当前网络隔离策略 / Get the current network isolation policy

        Returns:
            当前策略对象
        """
        return self._policy

    def _is_private_ip(self, hostname: str) -> bool:
        """检查主机名是否为私有 IP / Check if hostname is a private IP

        Args:
            hostname: 主机名或 IP 地址

        Returns:
            True 如果是私有 IP
        """
        try:
            ip = ipaddress.ip_address(socket.getaddrinfo(hostname, None)[0][4][0])
            for cidr in _PRIVATE_CIDRS:
                if ip in ipaddress.ip_network(cidr, strict=False):
                    return True
            return False
        except Exception:
            return False

    def _is_localhost(self, hostname: str) -> bool:
        """检查是否为本机地址 / Check if hostname is localhost

        Args:
            hostname: 主机名

        Returns:
            True 如果是本机地址
        """
        local_names = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
        if hostname.lower() in local_names:
            return True
        return False

    def _is_blocked(self, hostname: str) -> bool:
        """检查域名是否在黑名单中 / Check if domain is in the blocklist

        Args:
            hostname: 主机名

        Returns:
            True 如果在黑名单中
        """
        normalized = hostname.lower().strip()
        for blocked in self._policy.blocked_domains:
            if normalized == blocked or normalized.endswith(f".{blocked}"):
                return True
        return False

    def _is_allowed(self, hostname: str) -> bool:
        """检查域名是否在白名单中 / Check if domain is in the whitelist

        Args:
            hostname: 主机名

        Returns:
            True 如果在白名单中
        """
        normalized = hostname.lower().strip()
        for allowed in self._policy.allowed_domains:
            if normalized == allowed or normalized.endswith(f".{allowed}"):
                return True
        return False


_isolator: NetworkIsolator | None = None


def get_network_isolator(
    policy: NetworkIsolationPolicy | None = None,
) -> NetworkIsolator:
    """获取 NetworkIsolator 单例 / Get NetworkIsolator singleton

    Args:
        policy: 网络隔离策略，如果为 None 则使用默认策略

    Returns:
        NetworkIsolator 实例
    """
    global _isolator
    if _isolator is None or policy is not None:
        _isolator = NetworkIsolator(policy=policy)
    return _isolator
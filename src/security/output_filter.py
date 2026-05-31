# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 内置过滤规则 / Built-in filter rules
# 每条规则: (pattern, replacement, category)
_BUILTIN_RULES: list[tuple[str, str, str]] = [
    # API Key / Token 泄露
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED-API-KEY]', 'api_key'),
    (r'api_key[\s]*=[\s]*["\']?[a-zA-Z0-9]{16,}["\']?', '[REDACTED-API-KEY]', 'api_key'),
    (r'api[-_]?key[\s]*[:=][\s]*["\']?[a-zA-Z0-9]{16,}["\']?', '[REDACTED-API-KEY]', 'api_key'),
    (r'bearer[\s]+[a-zA-Z0-9\-._~+/]{20,}', '[REDACTED-TOKEN]', 'token'),
    (r'token[\s]*[:=][\s]*["\']?[a-zA-Z0-9\-._~+/]{16,}["\']?', '[REDACTED-TOKEN]', 'token'),
    (r'secret[\s]*[:=][\s]*["\']?[a-zA-Z0-9]{16,}["\']?', '[REDACTED-SECRET]', 'secret'),
    # 电话号码（11位手机号）
    (r'(?<!\d)1[3-9]\d{9}(?!\d)', '[REDACTED-PHONE]', 'phone'),
    # 身份证号（18位）
    (r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)', '[REDACTED-ID-CARD]', 'id_card'),
    # 银行卡号（16-19位数字）
    (r'(?<!\d)\d{16,19}(?!\d)', '[REDACTED-BANK-CARD]', 'bank_card'),
    # 内部路径泄露
    (r'/etc/(?!hostname|resolv\.conf|localtime)[a-zA-Z0-9_./-]+', '[REDACTED-PATH]', 'internal_path'),
    (r'/var/[a-zA-Z0-9_./-]+', '[REDACTED-PATH]', 'internal_path'),
    (r'/home/[a-zA-Z0-9_./-]+', '[REDACTED-PATH]', 'internal_path'),
    (r'/root/[a-zA-Z0-9_./-]+', '[REDACTED-PATH]', 'internal_path'),
    (r'C:\\Users\\[a-zA-Z0-9_./\\-]+', '[REDACTED-PATH]', 'internal_path'),
    (r'/proc/[a-zA-Z0-9_./-]+', '[REDACTED-PATH]', 'internal_path'),
    # 环境变量泄露
    (r'\$\{[A-Z_][A-Z0-9_]*\}', '[REDACTED-ENV-VAR]', 'env_var'),
    (r'(?i)(?:export|set|env)[\s]+[A-Z_][A-Z0-9_]*[\s]*=', '[REDACTED-ENV-SET]', 'env_var'),
    (r'(?:AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GOOGLE_API_KEY|OPENAI_API_KEY)'
     r'[\s]*[:=][\s]*["\']?[a-zA-Z0-9/+]{16,}["\']?', '[REDACTED-ENV-VAR]', 'env_var'),
    # 数据库连接字符串泄露
    (r'(?:mysql|postgres|mongodb|redis)://[^\s]{8,}@', '[REDACTED-DB-URL]', 'database_url'),
    # SSH 私钥泄露
    (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', '[REDACTED-PRIVATE-KEY]', 'private_key'),
]


class OutputFilter:
    """LLM 输出安全过滤器 / LLM output security filter

    使用正则表达式匹配并替换敏感信息，防止 LLM 输出中包含敏感数据。
    """

    def __init__(self, rules: list[tuple[str, str, str]] | None = None) -> None:
        self._rules: list[tuple[re.Pattern[str], str, str]] = []
        self._rule_categories: set[str] = set()

        initial_rules = rules if rules is not None else _BUILTIN_RULES
        for pattern, replacement, category in initial_rules:
            self.add_rule(pattern, replacement, category)

    def add_rule(self, pattern: str, replacement: str, category: str = "custom") -> None:
        """添加自定义过滤规则 / Add a custom filter rule

        Args:
            pattern: 正则表达式模式
            replacement: 替换文本
            category: 规则分类
        """
        compiled = re.compile(pattern, re.IGNORECASE)
        self._rules.append((compiled, replacement, category))
        self._rule_categories.add(category)
        logger.debug("过滤规则已添加: %s [%s]", pattern, category)

    def filter(self, text: str) -> tuple[str, list[str]]:
        """过滤文本中的敏感信息 / Filter sensitive information from text

        Args:
            text: 待过滤的文本

        Returns:
            (过滤后文本, 触发规则列表) 的元组
        """
        filtered = text
        triggered: list[str] = []

        for compiled_pattern, replacement, category in self._rules:
            if compiled_pattern.search(filtered):
                filtered = compiled_pattern.sub(replacement, filtered)
                if category not in triggered:
                    triggered.append(category)

        if triggered:
            logger.info(
                "输出过滤触发了 %d 条规则: %s / Output filter triggered %d rules: %s",
                len(triggered),
                ", ".join(triggered),
                len(triggered),
                ", ".join(triggered),
            )

        return filtered, triggered

    def contains_sensitive_info(self, text: str) -> bool:
        """检测文本是否包含敏感信息 / Check if text contains sensitive information

        Args:
            text: 待检测的文本

        Returns:
            True 如果包含敏感信息
        """
        for compiled_pattern, _replacement, _category in self._rules:
            if compiled_pattern.search(text):
                return True
        return False

    def get_categories(self) -> list[str]:
        """获取所有规则分类 / Get all rule categories

        Returns:
            规则分类列表
        """
        return list(self._rule_categories)


_filter: OutputFilter | None = None


def get_output_filter(rules: list[tuple[str, str, str]] | None = None) -> OutputFilter:
    """获取 OutputFilter 单例 / Get OutputFilter singleton

    Args:
        rules: 自定义过滤规则，如果为 None 则使用内置规则

    Returns:
        OutputFilter 实例
    """
    global _filter
    if _filter is None or rules is not None:
        _filter = OutputFilter(rules=rules)
    return _filter
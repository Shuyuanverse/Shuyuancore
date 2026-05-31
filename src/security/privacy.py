# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 内置脱敏规则（中文）/ Built-in desensitization rules (Chinese)
# 每条规则: (pattern, replacement, name)
_ZH_RULES: list[tuple[str, str, str]] = [
    # 手机号：138****8008
    (r'(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)', r'\1****\2', 'phone'),
    # 身份证：保留前3后4
    (r'(?<!\d)([1-9]\d{2})\d{11}(\d{4})(?!\d)', r'\1***********\2', 'id_card'),
    (r'(?<!\d)([1-9]\d{2})\d{11}(\d{4}[\dXx])(?!\d)', r'\1***********\2', 'id_card'),
    # 银行卡：**** **** **** 1234
    (r'(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)', r'\1 **** **** \2', 'bank_card'),
    # 邮箱：u***@example.com
    (r'(\w)[^@\s]*(@[\w.]+)', r'\1***\2', 'email'),
    # IP 地址：保留前两段 192.168.*.*
    (r'(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}', r'\1.*.*', 'ip_address'),
    # 姓名：保留姓氏
    (r'([\u4e00-\u9fa5])[\u4e00-\u9fa5]{1,2}(?=\s|$|[，。、；：])', r'\1**', 'name'),
    # 统一社会信用代码
    (r'(?<!\d)[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?!\d)', '[REDACTED-CODE]', 'credit_code'),
]

# 内置脱敏规则（英文）/ Built-in desensitization rules (English)
_EN_RULES: list[tuple[str, str, str]] = [
    # Phone: 138****8008
    (r'(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)', r'\1****\2', 'phone'),
    # ID Card: keep first 3 last 4
    (r'(?<!\d)([1-9]\d{2})\d{11}(\d{4})(?!\d)', r'\1***********\2', 'id_card'),
    (r'(?<!\d)([1-9]\d{2})\d{11}(\d{4}[\dXx])(?!\d)', r'\1***********\2', 'id_card'),
    # Bank card: **** **** **** 1234
    (r'(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)', r'\1 **** **** \2', 'bank_card'),
    # Email: u***@example.com
    (r'(\w)[^@\s]*(@[\w.]+)', r'\1***\2', 'email'),
    # IP: keep first two segments 192.168.*.*
    (r'(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}', r'\1.*.*', 'ip_address'),
    # Name: keep first character
    (r'([A-Z])[a-z]+(?:\s+[A-Z][a-z]+)*', r'\1.**', 'name'),
]

# 所有语言都应用的通用规则 / Common rules applied to all languages
_COMMON_RULES: list[tuple[str, str, str]] = []


class PrivacyDesensitizer:
    """隐私脱敏器 / Privacy desensitizer

    对文本和字典中的敏感信息进行脱敏处理，支持按国家/地区切换规则。
    """

    def __init__(self, locale: str = "zh", rules: list[tuple[str, str, str]] | None = None) -> None:
        self._locale: str = locale
        self._rules: list[tuple[str, str, str]] = []

        if rules is not None:
            self._rules = list(rules)
        else:
            self._rules = list(_COMMON_RULES)
            if locale == "en":
                self._rules.extend(_EN_RULES)
            else:
                self._rules.extend(_ZH_RULES)

        self._compiled: list[tuple[re.Pattern[str], str, str]] = [
            (re.compile(pattern), replacement, name)
            for pattern, replacement, name in self._rules
        ]

    def desensitize(self, text: str, rules: list[str] | None = None) -> str:
        """对文本进行脱敏处理 / Desensitize text

        Args:
            text: 待脱敏的文本
            rules: 要应用的规则名称列表。如果为 None，应用所有规则。

        Returns:
            脱敏后的文本
        """
        result = text
        for compiled_pattern, replacement, name in self._compiled:
            if rules is None or name in rules:
                result = compiled_pattern.sub(replacement, result)
        return result

    def desensitize_dict(
        self,
        data: dict[str, Any],
        sensitive_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """对字典中的敏感字段进行脱敏 / Desensitize sensitive fields in a dict

        Args:
            data: 待脱敏的字典
            sensitive_keys: 敏感键名列表。如果为 None，自动检测并脱敏所有字符串值。

        Returns:
            脱敏后的字典
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                if sensitive_keys is None or key in sensitive_keys:
                    result[key] = self.desensitize(value)
                else:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self.desensitize_dict(
                    value,
                    sensitive_keys=sensitive_keys,
                )
            elif isinstance(value, list):
                result[key] = [
                    self.desensitize(item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def add_custom_rule(self, pattern: str, replacement: str) -> None:
        """添加自定义脱敏规则 / Add a custom desensitization rule

        Args:
            pattern: 正则表达式模式
            replacement: 替换文本
        """
        compiled = re.compile(pattern)
        self._compiled.append((compiled, replacement, "custom"))
        self._rules.append((pattern, replacement, "custom"))
        logger.debug("自定义脱敏规则已添加: %s / Custom rule added: %s", pattern, pattern)

    def set_locale(self, locale: str) -> None:
        """切换语言区域 / Switch locale

        Args:
            locale: 语言代码（"zh" 或 "en"）
        """
        if locale == self._locale:
            return
        self._locale = locale
        self._rules = list(_COMMON_RULES)
        if locale == "en":
            self._rules.extend(_EN_RULES)
        else:
            self._rules.extend(_ZH_RULES)
        self._compiled = [
            (re.compile(pattern), replacement, name)
            for pattern, replacement, name in self._rules
        ]
        logger.info("隐私脱敏区域已切换为: %s / Privacy desensitizer locale changed to: %s", locale, locale)


_desensitizer: PrivacyDesensitizer | None = None
_desensitizer_lock: Any = None


def get_desensitizer(locale: str = "zh") -> PrivacyDesensitizer:
    """获取 PrivacyDesensitizer 单例 / Get PrivacyDesensitizer singleton

    Args:
        locale: 语言区域（"zh" 或 "en"），仅在首次创建时生效

    Returns:
        PrivacyDesensitizer 实例
    """
    global _desensitizer
    if _desensitizer is None:
        _desensitizer = PrivacyDesensitizer(locale=locale)
    return _desensitizer
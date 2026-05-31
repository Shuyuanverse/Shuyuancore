# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_HAS_CRYPTOGRAPHY: bool = False

try:
    from cryptography.fernet import Fernet, InvalidToken as CryptoInvalidToken

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    Fernet = None  # type: ignore[assignment, misc]
    CryptoInvalidToken = Exception  # type: ignore[assignment, misc]


def _check_crypto_available() -> bool:
    """检查 cryptography 库是否可用 / Check if cryptography library is available

    Returns:
        True 如果 cryptography 可用
    """
    return _HAS_CRYPTOGRAPHY


def _generate_key() -> bytes:
    """生成加密密钥 / Generate an encryption key

    优先从环境变量 ENCRYPTION_KEY 读取，否则生成新密钥。

    Returns:
        bytes 格式的密钥
    """
    env_key = os.environ.get("ENCRYPTION_KEY")
    if env_key:
        try:
            if _HAS_CRYPTOGRAPHY and Fernet is not None:
                return Fernet.generate_key() if len(env_key) < 32 else env_key.encode()
            return env_key.encode()
        except Exception:
            logger.warning("环境变量 ENCRYPTION_KEY 无效，将生成新密钥")
    if _HAS_CRYPTOGRAPHY and Fernet is not None:
        key = Fernet.generate_key()
        logger.info("已生成新的加密密钥 / New encryption key generated")
        return key
    raw = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    return raw.encode()


class DataEncryptor:
    """数据加密器 / Data encryptor

    使用 Fernet（对称加密）进行数据加密。如果 cryptography 不可用，
    自动降级为 hashlib 哈希处理（不可逆），并记录警告。

    Attributes:
        key: 当前使用的加密密钥
    """

    def __init__(self, key: bytes | str | None = None) -> None:
        if isinstance(key, str):
            key = key.encode()
        self._key: bytes = key if key is not None else _generate_key()
        self._fernet: Any = None

        if _HAS_CRYPTOGRAPHY and Fernet is not None:
            try:
                self._fernet = Fernet(self._key if isinstance(self._key, bytes) else self._key.encode())
            except Exception:
                self._fernet = Fernet(Fernet.generate_key())
                logger.warning("无法使用提供的密钥初始化 Fernet，已使用新密钥")
        else:
            logger.warning(
                "cryptography 不可用，降级为 hashlib 不可逆哈希处理 / "
                "cryptography not available, falling back to irreversible hashlib hashing"
            )

    def encrypt(self, data: str) -> str:
        """加密字符串 / Encrypt a string

        Args:
            data: 要加密的明文

        Returns:
            base64 编码的密文
        """
        if self._fernet is not None:
            encrypted = self._fernet.encrypt(data.encode())
            return base64.b64encode(encrypted).decode()
        hash_val = hashlib.sha256(data.encode()).hexdigest()
        logger.warning("降级模式：数据不可逆加密 / Fallback mode: irreversible encryption")
        return base64.b64encode(hash_val.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        """解密字符串 / Decrypt an encrypted string

        Args:
            encrypted: base64 编码的密文

        Returns:
            解密后的明文

        Raises:
            ValueError: 解密失败
        """
        if self._fernet is not None:
            try:
                raw = base64.b64decode(encrypted)
                return self._fernet.decrypt(raw).decode()
            except CryptoInvalidToken as e:
                raise ValueError(f"解密失败: {e} / Decryption failed: {e}") from e
        raise ValueError(
            "降级模式不支持解密 / Decryption not supported in fallback mode"
        )

    def encrypt_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """加密字典中所有字符串值 / Encrypt all string values in a dict

        Args:
            data: 要加密的字典

        Returns:
            加密后的字典（字符串值被加密，非字符串值保持不变）
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.encrypt(value)
            elif isinstance(value, dict):
                result[key] = self.encrypt_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.encrypt(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def decrypt_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """解密字典中所有加密的字符串值 / Decrypt all encrypted string values in a dict

        Args:
            data: 要解密的字典

        Returns:
            解密后的字典
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    result[key] = self.decrypt(value)
                except ValueError:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self.decrypt_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.decrypt(item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def rotate_key(self, new_key: bytes | str | None = None) -> None:
        """轮换加密密钥 / Rotate encryption key

        使用新密钥更新加密器。如果 cryptography 不可用，此操作无效果。

        Args:
            new_key: 新密钥，如果为 None 则生成新密钥
        """
        if not _HAS_CRYPTOGRAPHY:
            logger.warning("降级模式下不支持密钥轮换 / Key rotation not supported in fallback mode")
            return

        if isinstance(new_key, str):
            new_key = new_key.encode()
        self._key = new_key if new_key is not None else _generate_key()
        if Fernet is not None:
            self._fernet = Fernet(self._key)
        logger.info("加密密钥已轮换 / Encryption key rotated")


_encryptor: DataEncryptor | None = None


def get_encryptor(key: bytes | str | None = None) -> DataEncryptor:
    """获取 DataEncryptor 单例 / Get DataEncryptor singleton

    Args:
        key: 加密密钥，如果为 None 则使用已有实例或环境变量

    Returns:
        DataEncryptor 实例
    """
    global _encryptor
    if _encryptor is None or key is not None:
        _encryptor = DataEncryptor(key=key)
    return _encryptor
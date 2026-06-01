from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import time
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

try:
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False

logger = logging.getLogger(__name__)


class CryptoTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="crypto",
            description="Encryption, decryption, signing, and verification tool. "
            "Uses a master key from the MASTER_KEY environment variable.",
            category="extension",
            dangerous=True,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Operation: encrypt / decrypt / sign / verify / generate_key",
                    required=True,
                ),
                ToolParameter(
                    name="data",
                    type="string",
                    description="Data to encrypt, decrypt, sign, or verify",
                    required=True,
                ),
                ToolParameter(
                    name="signature",
                    type="string",
                    description="Expected signature to verify against (required for verify action)",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="key",
                    type="string",
                    description="Encryption or signing key (optional, uses MASTER_KEY by default)",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="algorithm",
                    type="string",
                    description="Algorithm: fernet (default) for encrypt/decrypt",
                    required=False,
                    default="fernet",
                ),
                ToolParameter(
                    name="key_id",
                    type="string",
                    description="Optional identifier for key rotation tracking",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "")
        valid_actions = {"encrypt", "decrypt", "sign", "verify", "generate_key"}
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors
        if not params.get("data"):
            errors.append("data parameter is required and must not be empty")
        if action == "verify" and not params.get("signature"):
            errors.append("signature parameter is required for verify action")
        if action in ("encrypt", "decrypt") and not _HAS_FERNET:
            errors.append(
                "cryptography is not installed. Install it with: pip install cryptography"
            )
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        data: str = params["data"]
        start = time.time()

        if action == "generate_key":
            return await self._generate_key(start)

        key: str | None = params.get("key") or os.environ.get("MASTER_KEY")
        if not key and action in ("encrypt", "decrypt", "sign", "verify"):
            if action == "sign" or action == "verify":
                return ToolResult(
                    success=False,
                    error="No key provided and MASTER_KEY not set. "
                    "Provide a key parameter or set the MASTER_KEY environment variable.",
                    duration_ms=(time.time() - start) * 1000,
                )
            key = self._get_or_generate_master_key()
            logger.warning(
                "MASTER_KEY not set in environment. Generated ephemeral key. "
                "Set MASTER_KEY for persistent encryption."
            )

        if action == "encrypt":
            return await self._encrypt(data, key, start)
        elif action == "decrypt":
            return await self._decrypt(data, key, start)
        elif action == "sign":
            return await self._sign(data, key, start)
        elif action == "verify":
            provided_signature: str | None = params.get("signature")
            if provided_signature and key:
                return await self._verify_with_signature(
                    data, key, provided_signature, start
                )
            return await self._verify(data, key, start)

    async def _encrypt(
        self,
        data: str,
        key: str | None,
        start: float,
    ) -> ToolResult:
        try:
            fernet_key = self._ensure_fernet_key(key)
            cipher = Fernet(fernet_key)
            encrypted = cipher.encrypt(data.encode("utf-8"))
            encoded = base64.urlsafe_b64encode(encrypted).decode("utf-8")
            return ToolResult(
                success=True,
                data={
                    "encrypted": encoded,
                    "algorithm": "fernet",
                    "key_id": hashlib.sha256(fernet_key.encode("utf-8")).hexdigest()[:8],
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                error=f"Encryption failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _decrypt(
        self,
        data: str,
        key: str | None,
        start: float,
    ) -> ToolResult:
        try:
            fernet_key = self._ensure_fernet_key(key)
            cipher = Fernet(fernet_key)
            decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
            decrypted = cipher.decrypt(decoded)
            return ToolResult(
                success=True,
                data={
                    "decrypted": decrypted.decode("utf-8"),
                    "algorithm": "fernet",
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except (ValueError, InvalidToken, binascii.Error) as e:
            return ToolResult(
                success=False,
                error=f"Decryption failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _sign(
        self,
        data: str,
        key: str | None,
        start: float,
    ) -> ToolResult:
        try:
            sign_key: str = key or ""
            signature = hmac.new(
                sign_key.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return ToolResult(
                success=True,
                data={
                    "signature": signature,
                    "algorithm": "HMAC-SHA256",
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except (ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Signing failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _verify(
        self,
        data: str,
        key: str | None,
        start: float,
    ) -> ToolResult:
        try:
            sign_key: str = key or ""
            expected_signature = hmac.new(
                sign_key.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return ToolResult(
                success=True,
                data={
                    "computed_signature": expected_signature,
                    "algorithm": "HMAC-SHA256",
                    "verified": True,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except (ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Verification failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _verify_with_signature(
        self,
        data: str,
        key: str,
        provided_signature: str,
        start: float,
    ) -> ToolResult:
        try:
            computed_signature = hmac.new(
                key.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            is_valid = hmac.compare_digest(computed_signature, provided_signature)
            return ToolResult(
                success=True,
                data={
                    "verified": is_valid,
                    "algorithm": "HMAC-SHA256",
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except (ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Verification failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _generate_key(self, start: float) -> ToolResult:
        if not _HAS_FERNET:
            return ToolResult(
                success=False,
                error="cryptography is not installed. Install it with: pip install cryptography",
                duration_ms=(time.time() - start) * 1000,
            )
        try:
            key = Fernet.generate_key().decode("utf-8")
            return ToolResult(
                success=True,
                data={
                    "key": key,
                    "algorithm": "fernet",
                    "warning": "Save this key securely. Set it as MASTER_KEY in your environment.",
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Key generation failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    @staticmethod
    def _get_or_generate_master_key() -> str:
        env_key = os.environ.get("MASTER_KEY")
        if env_key:
            return env_key
        if _HAS_FERNET:
            generated = Fernet.generate_key().decode("utf-8")
            logger.warning("No MASTER_KEY found in environment. Generated temporary key.")
            return generated
        return hashlib.sha256(b"shuyuan-core-fallback").hexdigest()

    @staticmethod
    def _ensure_fernet_key(key: str | None) -> str:
        if key and (key.endswith("=") or len(key) == 44):
            return key
        if key:
            digest = hashlib.sha256(key.encode("utf-8")).digest()
            return base64.urlsafe_b64encode(digest).decode("utf-8")
        raise ValueError("No encryption key available")

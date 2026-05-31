from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.tools.builtin.crypto import CryptoTool


class TestCryptoTool:

    def test_crypto_get_spec(self) -> None:
        tool = CryptoTool()
        spec = tool.get_spec()
        assert spec.name == "crypto"
        assert spec.category == "extension"
        assert spec.dangerous is True

    @pytest.mark.asyncio
    async def test_crypto_validate_empty_data(self) -> None:
        tool = CryptoTool()
        errors = await tool.validate({"action": "encrypt", "data": ""})
        assert len(errors) >= 1
        assert any("data" in e for e in errors)

    @pytest.mark.asyncio
    async def test_crypto_validate_valid(self) -> None:
        tool = CryptoTool()
        errors = await tool.validate({"action": "sign", "data": "hello"})
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_crypto_execute_encrypt_decrypt(self) -> None:
        mock_cipher = MagicMock()
        mock_cipher.encrypt.return_value = b"encrypted_token"
        mock_cipher.decrypt.return_value = b"original_data"
        valid_key = "dGVzdC1rZXktZm9yLXRlc3RpbmctcHVycG9zZXM="

        tool = CryptoTool()
        with patch("src.tools.builtin.crypto._HAS_FERNET", True), \
             patch("os.environ", {"MASTER_KEY": valid_key}), \
             patch("src.tools.builtin.crypto.Fernet", return_value=mock_cipher):
            enc_result = await tool.execute({
                "action": "encrypt",
                "data": "original_data",
            })

        assert enc_result.success
        assert enc_result.data["algorithm"] == "fernet"
        assert "encrypted" in enc_result.data

        with patch("src.tools.builtin.crypto._HAS_FERNET", True), \
             patch("os.environ", {"MASTER_KEY": valid_key}), \
             patch("src.tools.builtin.crypto.Fernet", return_value=mock_cipher):
            dec_result = await tool.execute({
                "action": "decrypt",
                "data": enc_result.data["encrypted"],
            })

        assert dec_result.success
        assert dec_result.data["decrypted"] == "original_data"

    @pytest.mark.asyncio
    async def test_crypto_execute_generate_key(self) -> None:
        mock_key_bytes = (
            b"dGVzdC1rZXktZm9yLXRlc3RpbmctcHVycG9zZXM="
        )

        tool = CryptoTool()
        with patch("src.tools.builtin.crypto._HAS_FERNET", True), \
             patch(
                 "src.tools.builtin.crypto.Fernet.generate_key",
                 return_value=mock_key_bytes,
             ):
            result = await tool.execute({
                "action": "generate_key",
                "data": "",
            })

        assert result.success
        assert result.data["algorithm"] == "fernet"
        assert result.data["key"].endswith("=")

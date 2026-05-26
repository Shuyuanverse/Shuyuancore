from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.builtin.email import EmailTool


class TestEmailTool:

    def test_email_get_spec(self) -> None:
        tool = EmailTool()
        spec = tool.get_spec()
        assert spec.name == "email"
        assert spec.category == "web"

    @pytest.mark.asyncio
    async def test_email_validate_invalid_action(self) -> None:
        tool = EmailTool()
        errors = await tool.validate({"action": "delete"})
        assert len(errors) == 1
        assert "action" in errors[0]

    @pytest.mark.asyncio
    async def test_email_validate_missing_to(self) -> None:
        tool = EmailTool()
        errors = await tool.validate({"action": "send"})
        assert len(errors) == 1
        assert "to" in errors[0]

    @pytest.mark.asyncio
    async def test_email_validate_valid(self) -> None:
        tool = EmailTool()
        errors_send = await tool.validate({
            "action": "send",
            "to": "user@example.com",
            "subject": "Hello",
            "body": "Test",
        })
        assert len(errors_send) == 0

        errors_list = await tool.validate({"action": "list"})
        assert len(errors_list) == 0

        errors_read = await tool.validate({
            "action": "read",
            "msg_id": "1",
        })
        assert len(errors_read) == 0

    @pytest.mark.asyncio
    async def test_email_execute_send_approved(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.com")
        monkeypatch.setenv("EMAIL_IMAP_PORT", "993")
        monkeypatch.setenv("EMAIL_USER", "test@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "secret")

        mock_mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.approval_id = "apr_send"
        mock_mgr.request = AsyncMock(return_value=mock_req)
        mock_mgr.wait = AsyncMock(return_value=True)

        mock_smtp = MagicMock()

        tool = EmailTool()
        with (
            patch(
                "src.tools.builtin.email.get_approval_manager",
                return_value=mock_mgr,
            ),
            patch(
                "src.tools.builtin.email.smtplib.SMTP",
                return_value=mock_smtp,
            ),
        ):
            result = await tool.execute({
                "action": "send",
                "to": "recipient@example.com",
                "subject": "Test Subject",
                "body": "Hello from test",
            })
            assert result.success
            assert result.data["to"] == "recipient@example.com"
            assert result.data["subject"] == "Test Subject"

    @pytest.mark.asyncio
    async def test_email_execute_list(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.com")
        monkeypatch.setenv("EMAIL_IMAP_PORT", "993")
        monkeypatch.setenv("EMAIL_USER", "test@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "secret")

        mock_client = MagicMock()
        mock_client.login = MagicMock()
        mock_client.select = MagicMock()
        mock_client.search = MagicMock(return_value=("OK", [b"1 2 3"]))
        mock_client.fetch = MagicMock(
            return_value=(
                "OK",
                [
                    (
                        b"1 (FLAGS (\\Seen))",
                        (
                            b"From: sender@example.com\r\n"
                            b"Subject: Test\r\n"
                            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\n"
                        ),
                    ),
                ],
            ),
        )
        mock_client.close = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)

        tool = EmailTool()
        with (
            patch(
                "src.tools.builtin.email.get_approval_manager",
                return_value=MagicMock(),
            ),
            patch(
                "src.tools.builtin.email.imaplib.IMAP4_SSL",
                return_value=mock_client,
            ),
        ):
            result = await tool.execute({
                "action": "list",
                "folder": "INBOX",
                "limit": 5,
            })
            assert result.success
            assert result.data["count"] > 0
            assert result.data["folder"] == "INBOX"

    @pytest.mark.asyncio
    async def test_email_execute_not_configured(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
        monkeypatch.delenv("EMAIL_SMTP_PORT", raising=False)
        monkeypatch.delenv("EMAIL_IMAP_HOST", raising=False)
        monkeypatch.delenv("EMAIL_IMAP_PORT", raising=False)
        monkeypatch.delenv("EMAIL_USER", raising=False)
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

        tool = EmailTool()
        result = await tool.execute({
            "action": "list",
        })
        assert not result.success
        assert "not configured" in result.error
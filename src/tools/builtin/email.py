from __future__ import annotations

import email
import imaplib
import os
import smtplib
import time
from email.message import EmailMessage
from email.policy import default as email_policy
from typing import Any

from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

_ENV_SMTP_HOST = "EMAIL_SMTP_HOST"
_ENV_SMTP_PORT = "EMAIL_SMTP_PORT"
_ENV_IMAP_HOST = "EMAIL_IMAP_HOST"
_ENV_IMAP_PORT = "EMAIL_IMAP_PORT"
_ENV_USER = "EMAIL_USER"
_ENV_PASSWORD = "EMAIL_PASSWORD"


class EmailTool(ITool):

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="email",
            description="邮件工具，支持通过 SMTP 发送邮件和通过 IMAP 列出/读取邮件。",
            category="web",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="操作类型：send（发送）/ list（列表）/ read（读取）",
                    required=True,
                ),
                ToolParameter(
                    name="to",
                    type="string",
                    description="收件人地址，send 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    description="邮件主题",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="邮件正文",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="列表返回数量上限，list 操作使用",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="folder",
                    type="string",
                    description="邮件文件夹，list/read 操作使用",
                    required=False,
                    default="INBOX",
                ),
                ToolParameter(
                    name="msg_id",
                    type="string",
                    description="邮件 ID，read 操作必填",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action = params.get("action", "")
        valid_actions = {"send", "list", "read"}
        if action not in valid_actions:
            errors.append(f"action 必须是 {', '.join(sorted(valid_actions))}")
            return errors
        if action == "send":
            to = params.get("to")
            if not to:
                errors.append("send 操作必须提供 to 参数")
        if action == "read":
            msg_id = params.get("msg_id")
            if not msg_id:
                errors.append("read 操作必须提供 msg_id 参数")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        smtp_host = os.environ.get(_ENV_SMTP_HOST)
        smtp_port_str = os.environ.get(_ENV_SMTP_PORT, "587")
        imap_host = os.environ.get(_ENV_IMAP_HOST)
        imap_port_str = os.environ.get(_ENV_IMAP_PORT, "993")
        email_user = os.environ.get(_ENV_USER)
        email_password = os.environ.get(_ENV_PASSWORD)

        if not all([smtp_host, imap_host, email_user, email_password]):
            return ToolResult(
                success=False,
                error="Email not configured",
                duration_ms=(time.time() - start) * 1000,
            )

        smtp_port = int(smtp_port_str)
        imap_port = int(imap_port_str)

        if action == "send":
            return await self._send_email(
                params, user_id, start, audit,
                smtp_host, smtp_port, email_user, email_password,
            )
        elif action == "list":
            return await self._list_emails(
                params, user_id, start, audit,
                imap_host, imap_port, email_user, email_password,
            )
        else:
            return await self._read_email(
                params, user_id, start, audit,
                imap_host, imap_port, email_user, email_password,
            )

    async def _send_email(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
        smtp_host: str,
        smtp_port: int,
        email_user: str,
        email_password: str,
    ) -> ToolResult:
        approval_mgr = get_approval_manager()
        req = await approval_mgr.request(
            tool_name="email",
            params=params,
            user_id=user_id,
            timeout=300,
        )
        approved = await approval_mgr.wait(req.approval_id, timeout=300)
        if not approved:
            audit.log(
                user_id=user_id,
                action="email.send",
                resource="smtp",
                params={"to": params.get("to"), "subject": params.get("subject")},
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error="邮件发送未获批准",
                duration_ms=(time.time() - start) * 1000,
                approval_id=req.approval_id,
            )

        to: str = params["to"]
        subject: str = params.get("subject", "")
        body: str = params.get("body", "")

        try:
            msg = EmailMessage()
            msg["From"] = email_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()
                server.login(email_user, email_password)
                server.send_message(msg)

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.send",
                resource="smtp",
                params={"to": to, "subject": subject},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"to": to, "subject": subject},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.send",
                resource="smtp",
                params={"to": to, "subject": subject},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"邮件发送失败: {e}",
                duration_ms=duration_ms,
            )

    async def _list_emails(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
        imap_host: str,
        imap_port: int,
        email_user: str,
        email_password: str,
    ) -> ToolResult:
        folder: str = params.get("folder", "INBOX")
        limit: int = params.get("limit", 10)

        try:
            with imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30) as client:
                client.login(email_user, email_password)
                client.select(folder)

                typ, data = client.search(None, "ALL")
                if typ != "OK" or not data or not data[0]:
                    return ToolResult(
                        success=True,
                        data={"emails": [], "count": 0, "folder": folder},
                        duration_ms=(time.time() - start) * 1000,
                    )

                ids = data[0].split()
                recent_ids = ids[-limit:]

                emails: list[dict[str, Any]] = []
                for msg_id in recent_ids:
                    typ, fetch_data = client.fetch(
                        msg_id, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
                    )
                    if typ != "OK":
                        continue
                    summary = self._parse_list_response(
                        msg_id, fetch_data
                    )
                    if summary:
                        emails.append(summary)

                client.close()

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.list",
                resource=f"imap:{folder}",
                params={"folder": folder, "limit": limit},
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"emails": emails, "count": len(emails), "folder": folder},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.list",
                resource=f"imap:{folder}",
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"邮件列表获取失败: {e}",
                duration_ms=duration_ms,
            )

    async def _read_email(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
        imap_host: str,
        imap_port: int,
        email_user: str,
        email_password: str,
    ) -> ToolResult:
        folder: str = params.get("folder", "INBOX")
        msg_id: str = params["msg_id"]

        try:
            with imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30) as client:
                client.login(email_user, email_password)
                client.select(folder)

                typ, data = client.fetch(msg_id, "(FLAGS BODY.PEEK[])")
                if typ != "OK":
                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="email.read",
                        resource=f"imap:{folder}:{msg_id}",
                        result="error",
                        error=f"邮件 {msg_id} 不存在",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=False,
                        error=f"邮件 {msg_id} 不存在",
                        duration_ms=duration_ms,
                    )

                raw_email: bytes | None = None
                flags: list[str] = []
                for part in data:
                    if isinstance(part, tuple):
                        raw_email = part[1]
                        raw_flags = part[0]
                        if isinstance(raw_flags, bytes):
                            flags = self._parse_flags(raw_flags)

                if raw_email is None:
                    return ToolResult(
                        success=False,
                        error=f"邮件 {msg_id} 内容为空",
                        duration_ms=(time.time() - start) * 1000,
                    )

                parsed = email.message_from_bytes(
                    raw_email, policy=email_policy
                )
                email_data = self._parse_email_message(parsed, msg_id, flags)
                client.close()

            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.read",
                resource=f"imap:{folder}:{msg_id}",
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data=email_data,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="email.read",
                resource=f"imap:{folder}:{msg_id}",
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"邮件读取失败: {e}",
                duration_ms=duration_ms,
            )

    @staticmethod
    def _parse_list_response(
        msg_id: bytes,
        fetch_data: list[Any],
    ) -> dict[str, Any] | None:
        raw_header: bytes | None = None
        flags: list[str] = []
        for part in fetch_data:
            if isinstance(part, tuple):
                raw_header = part[1]
                raw_flags = part[0]
                if isinstance(raw_flags, bytes):
                    flags = EmailTool._parse_flags(raw_flags)

        if raw_header is None:
            return None

        msg = email.message_from_bytes(raw_header, policy=email_policy)
        return {
            "id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
            "from": msg.get("From", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "flags": flags,
        }

    @staticmethod
    def _parse_flags(raw_flags: bytes) -> list[str]:
        decoded = raw_flags.decode(errors="replace")
        parts = decoded.split()
        flags: list[str] = []
        for p in parts:
            p = p.strip("()")
            if p.startswith("\\"):
                flags.append(p)
        return flags

    @staticmethod
    def _parse_email_message(
        msg: email.message.Message,
        msg_id: str,
        flags: list[str],
    ) -> dict[str, Any]:
        body_text = ""
        body_html = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdisp = part.get_content_disposition()
                if cdisp == "attachment":
                    continue
                if ctype == "text/plain" and not body_text:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                elif ctype == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_html = payload.decode(charset, errors="replace")
        else:
            ctype = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                if ctype == "text/html":
                    body_html = payload.decode(charset, errors="replace")
                else:
                    body_text = payload.decode(charset, errors="replace")

        attachments: list[dict[str, str]] = []
        if msg.is_multipart():
            for part in msg.walk():
                cdisp = part.get_content_disposition()
                if cdisp == "attachment":
                    filename = part.get_filename() or "unnamed"
                    ctype = part.get_content_type()
                    attachments.append({
                        "filename": filename,
                        "type": ctype,
                    })

        return {
            "id": msg_id,
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "flags": flags,
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
        }

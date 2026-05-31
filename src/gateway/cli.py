from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any

from src.gateway.base_adapter import MessageEvent, PlatformAdapter

logger = logging.getLogger(__name__)


class CliAdapter(PlatformAdapter):
    """CLI 接入层适配器。

    在 REPL / 命令行模式下处理消息的收发。
    消息通过 stdout 打印输出，用户信息返回本地系统数据。
    """

    @property
    def platform_name(self) -> str:
        """获取平台名称。"""
        return "cli"

    async def send_message(
        self, user_id: str, message: str, conversation_id: str = ""
    ) -> str:
        """发送文本消息到 stdout。

        Args:
            user_id: 目标用户 ID（CLI 模式下通常为本地用户）
            message: 消息文本
            conversation_id: 会话 ID

        Returns:
            str: 消息 ID
        """
        message_id = str(uuid.uuid4())
        print(message, file=sys.stdout, flush=True)
        logger.info(
            "[cli] send_message: user=%s conv=%s msg_id=%s len=%d",
            user_id,
            conversation_id,
            message_id,
            len(message),
        )
        return message_id

    async def send_rich_message(
        self,
        user_id: str,
        content_type: str,
        content: dict[str, Any],
        conversation_id: str = "",
    ) -> str:
        """发送富文本消息到 stdout（格式化 JSON 输出）。

        Args:
            user_id: 目标用户 ID
            content_type: 内容类型
            content: 内容数据
            conversation_id: 会话 ID

        Returns:
            str: 消息 ID
        """
        message_id = str(uuid.uuid4())
        header = f"[{content_type.upper()}]"
        separator = "=" * 40
        body = json.dumps(content, ensure_ascii=False, indent=2)
        print(f"\n{separator}\n{header}\n{separator}\n{body}\n", file=sys.stdout, flush=True)
        logger.info(
            "[cli] send_rich_message: user=%s conv=%s type=%s msg_id=%s",
            user_id,
            conversation_id,
            content_type,
            message_id,
        )
        return message_id

    async def edit_message(
        self, conversation_id: str, message_id: str, new_content: str
    ) -> bool:
        """编辑消息（CLI 模式不支持）。

        Args:
            conversation_id: 会话 ID
            message_id: 要编辑的消息 ID
            new_content: 新的消息内容

        Returns:
            bool: 始终返回 False
        """
        logger.warning(
            "[cli] edit_message 在 CLI 模式下不支持: conv=%s msg_id=%s",
            conversation_id,
            message_id,
        )
        return False

    async def delete_message(
        self, conversation_id: str, message_id: str
    ) -> bool:
        """删除消息（CLI 模式不支持）。

        Args:
            conversation_id: 会话 ID
            message_id: 要删除的消息 ID

        Returns:
            bool: 始终返回 False
        """
        logger.warning(
            "[cli] delete_message 在 CLI 模式下不支持: conv=%s msg_id=%s",
            conversation_id,
            message_id,
        )
        return False

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取本地用户信息。

        Args:
            user_id: 用户 ID

        Returns:
            dict: 包含本地系统用户信息的字典
        """
        return {
            "user_id": user_id or os.environ.get("USER", "unknown"),
            "platform": "cli",
            "nickname": os.environ.get("USER", "local_user"),
            "shell": os.environ.get("SHELL", ""),
            "home": os.environ.get("HOME", ""),
        }

    async def validate_webhook(self, data: dict[str, Any]) -> bool:
        """验证 CLI 输入（CLI 模式始终返回 True）。

        Args:
            data: 输入数据

        Returns:
            bool: 始终返回 True
        """
        return True

    async def parse_webhook(
        self, data: dict[str, Any]
    ) -> MessageEvent | None:
        """解析 CLI 输入为 MessageEvent。

        Args:
            data: 输入数据，应包含 message 字段

        Returns:
            MessageEvent | None: 解析成功后的事件对象
        """
        message = data.get("message", "")
        if not message:
            return None

        return MessageEvent(
            platform=self.platform_name,
            user_id=data.get("user_id", os.environ.get("USER", "local")),
            message=message,
            message_type=data.get("message_type", "text"),
            conversation_id=data.get("conversation_id", ""),
            raw_data=data,
        )

    async def handle_event(self, event: MessageEvent) -> str | None:
        """处理 CLI 消息事件。

        Args:
            event: 消息事件

        Returns:
            str | None: 返回消息文本供上游处理
        """
        logger.info(
            "[cli] handle_event: event_id=%s msg=%s",
            event.event_id,
            event.message[:50] if event.message else "",
        )
        return event.message
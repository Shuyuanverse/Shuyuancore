from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MessageEvent:
    """平台消息事件的数据结构。

    Attributes:
        event_id: 事件唯一标识
        platform: 来源平台名称
        user_id: 发送者用户 ID
        message: 消息文本内容
        message_type: 消息类型（text, image, voice 等）
        timestamp: 事件产生时间戳
        conversation_id: 会话 ID
        raw_data: 原始请求数据
        metadata: 附加元数据
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: str = ""
    user_id: str = ""
    message: str = ""
    message_type: str = "text"
    timestamp: float = field(default_factory=time.time)
    conversation_id: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """平台适配器抽象基类。

    所有平台接入层（企业微信、CLI、API 等）必须实现此接口，
    以保证网关可以统一路由和管理消息。
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """获取平台名称。"""
        ...

    @abstractmethod
    async def send_message(
        self, user_id: str, message: str, conversation_id: str = ""
    ) -> str:
        """发送文本消息到指定用户。

        Args:
            user_id: 目标用户 ID
            message: 消息文本
            conversation_id: 会话 ID

        Returns:
            str: 发送成功的消息 ID
        """
        ...

    @abstractmethod
    async def send_rich_message(
        self,
        user_id: str,
        content_type: str,
        content: dict[str, Any],
        conversation_id: str = "",
    ) -> str:
        """发送富文本消息（图文、卡片、Markdown 等）。

        Args:
            user_id: 目标用户 ID
            content_type: 内容类型（markdown, image, card 等）
            content: 内容数据
            conversation_id: 会话 ID

        Returns:
            str: 发送成功的消息 ID
        """
        ...

    @abstractmethod
    async def edit_message(
        self, conversation_id: str, message_id: str, new_content: str
    ) -> bool:
        """编辑已发送的消息。

        Args:
            conversation_id: 会话 ID
            message_id: 要编辑的消息 ID
            new_content: 新的消息内容

        Returns:
            bool: 编辑是否成功
        """
        ...

    @abstractmethod
    async def delete_message(
        self, conversation_id: str, message_id: str
    ) -> bool:
        """删除已发送的消息。

        Args:
            conversation_id: 会话 ID
            message_id: 要删除的消息 ID

        Returns:
            bool: 删除是否成功
        """
        ...

    @abstractmethod
    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取用户信息。

        Args:
            user_id: 用户 ID

        Returns:
            dict: 用户信息字典
        """
        ...

    @abstractmethod
    async def validate_webhook(self, data: dict[str, Any]) -> bool:
        """验证 webhook 请求的合法性。

        Args:
            data: webhook 请求数据

        Returns:
            bool: 验证是否通过
        """
        ...

    @abstractmethod
    async def parse_webhook(
        self, data: dict[str, Any]
    ) -> MessageEvent | None:
        """解析 webhook 请求数据为 MessageEvent。

        Args:
            data: webhook 请求数据

        Returns:
            MessageEvent | None: 解析成功后的事件对象，无效请求返回 None
        """
        ...


class BaseAdapter(PlatformAdapter):
    """平台适配器基类，提供 PlatformAdapter 接口的默认实现。

    子类可以按需覆盖特定方法。本类提供了基础的日志记录和
    错误处理，降低子类实现门槛。
    """

    @property
    def platform_name(self) -> str:
        """获取平台名称，子类应覆盖此属性。"""
        return "base"

    async def send_message(
        self, user_id: str, message: str, conversation_id: str = ""
    ) -> str:
        """默认发送消息实现：记录日志并返回模拟 message_id。

        Args:
            user_id: 目标用户 ID
            message: 消息文本
            conversation_id: 会话 ID

        Returns:
            str: 模拟的消息 ID
        """
        message_id = str(uuid.uuid4())
        logger.info(
            "[%s] send_message: user=%s conv=%s msg_id=%s len=%d",
            self.platform_name,
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
        """默认富文本发送实现：记录日志。

        Args:
            user_id: 目标用户 ID
            content_type: 内容类型
            content: 内容数据
            conversation_id: 会话 ID

        Returns:
            str: 模拟的消息 ID
        """
        message_id = str(uuid.uuid4())
        logger.info(
            "[%s] send_rich_message: user=%s conv=%s type=%s msg_id=%s",
            self.platform_name,
            user_id,
            conversation_id,
            content_type,
            message_id,
        )
        return message_id

    async def edit_message(
        self, conversation_id: str, message_id: str, new_content: str
    ) -> bool:
        """默认编辑消息实现：记录日志并返回成功。

        Args:
            conversation_id: 会话 ID
            message_id: 要编辑的消息 ID
            new_content: 新的消息内容

        Returns:
            bool: True
        """
        logger.info(
            "[%s] edit_message: conv=%s msg_id=%s len=%d",
            self.platform_name,
            conversation_id,
            message_id,
            len(new_content),
        )
        return True

    async def delete_message(
        self, conversation_id: str, message_id: str
    ) -> bool:
        """默认删除消息实现：记录日志并返回成功。

        Args:
            conversation_id: 会话 ID
            message_id: 要删除的消息 ID

        Returns:
            bool: True
        """
        logger.info(
            "[%s] delete_message: conv=%s msg_id=%s",
            self.platform_name,
            conversation_id,
            message_id,
        )
        return True

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """默认获取用户信息实现：返回基础信息。

        Args:
            user_id: 用户 ID

        Returns:
            dict: 包含 user_id 和 platform 的基础信息
        """
        return {
            "user_id": user_id,
            "platform": self.platform_name,
            "nickname": user_id,
        }

    async def validate_webhook(self, data: dict[str, Any]) -> bool:
        """默认 webhook 验证实现。

        Args:
            data: webhook 请求数据

        Returns:
            bool: 子类应覆盖此方法
        """
        logger.warning(
            "[%s] validate_webhook called with default implementation",
            self.platform_name,
        )
        return True

    async def parse_webhook(
        self, data: dict[str, Any]
    ) -> MessageEvent | None:
        """默认 webhook 解析实现。

        Args:
            data: webhook 请求数据

        Returns:
            MessageEvent | None: 子类应覆盖此方法
        """
        logger.warning(
            "[%s] parse_webhook called with default implementation",
            self.platform_name,
        )
        return None

    async def handle_event(self, event: MessageEvent) -> str | None:
        """事件处理入口，接收 MessageEvent 并做前置处理。

        Args:
            event: 消息事件

        Returns:
            str | None: 处理结果文本，None 表示无需回复
        """
        logger.info(
            "[%s] handle_event: event_id=%s user=%s type=%s",
            self.platform_name,
            event.event_id,
            event.user_id,
            event.message_type,
        )
        return event.message
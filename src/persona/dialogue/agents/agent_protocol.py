# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""Agent 间通信协议。

包含：
- MessageType：消息类型枚举
- Priority：优先级枚举
- AgentMessage：Agent 间通信消息
- MessageBuilder：消息构建器（链式 API）
- Protocol：通信协议常量
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class MessageType(Enum):
    """消息类型"""

    REQUEST = "request"  # 请求
    RESPONSE = "response"  # 响应
    REVIEW = "review"  # 审视
    ARBITRATION = "arbitration"  # 仲裁
    ERROR = "error"  # 错误
    CONTROL = "control"  # 控制


class Priority(Enum):
    """优先级"""

    LOW = 1  # 低
    NORMAL = 2  # 普通
    HIGH = 3  # 高
    CRITICAL = 4  # 紧急


@dataclass
class AgentMessage:
    """Agent 间通信消息

    Attributes:
        message_type: 消息类型
        sender: 发送者
        receiver: 接收者
        content: 消息内容
        priority: 优先级
        metadata: 元数据
        timestamp: 时间戳
        message_id: 消息 ID
        parent_id: 父消息 ID（回复链追踪）
    """

    message_type: MessageType
    sender: str
    receiver: str
    content: Any
    priority: Priority = Priority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: Optional[str] = None  # 回复链追踪

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_type": self.message_type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "priority": self.priority.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentMessage:
        """从字典创建"""
        return cls(
            message_type=MessageType(data["message_type"]),
            sender=data["sender"],
            receiver=data["receiver"],
            content=data["content"],
            priority=Priority(data["priority"]),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time()),
            message_id=data.get("message_id", str(uuid4())),
            parent_id=data.get("parent_id"),
        )


class MessageBuilder:
    """消息构建器 — 链式 API

    使用示例：
    ```python
    msg = (MessageBuilder
           .request("decision", "review", {"response": "..."})
           .with_priority(Priority.HIGH)
           .with_metadata({"persona_id": "xxx"})
           .build())
    ```
    """

    def __init__(self):
        """初始化消息构建器"""
        self._message_type: Optional[MessageType] = None
        self._sender: str = ""
        self._receiver: str = ""
        self._content: Any = None
        self._priority: Priority = Priority.NORMAL
        self._metadata: Dict[str, Any] = {}

    @classmethod
    def request(
        cls,
        sender: str,
        receiver: str,
        content: Any,
    ) -> "MessageBuilder":
        """构建请求消息

        Args:
            sender: 发送者
            receiver: 接收者
            content: 消息内容

        Returns:
            MessageBuilder: 消息构建器
        """
        builder = cls()
        builder._message_type = MessageType.REQUEST
        builder._sender = sender
        builder._receiver = receiver
        builder._content = content
        return builder

    @classmethod
    def response(
        cls,
        sender: str,
        receiver: str,
        content: Any,
    ) -> "MessageBuilder":
        """构建响应消息

        Args:
            sender: 发送者
            receiver: 接收者
            content: 消息内容

        Returns:
            MessageBuilder: 消息构建器
        """
        builder = cls()
        builder._message_type = MessageType.RESPONSE
        builder._sender = sender
        builder._receiver = receiver
        builder._content = content
        return builder

    def with_priority(self, priority: Priority) -> "MessageBuilder":
        """设置优先级

        Args:
            priority: 优先级

        Returns:
            MessageBuilder: 消息构建器
        """
        self._priority = priority
        return self

    def with_metadata(self, metadata: Dict[str, Any]) -> "MessageBuilder":
        """设置元数据

        Args:
            metadata: 元数据

        Returns:
            MessageBuilder: 消息构建器
        """
        self._metadata = metadata
        return self

    def with_parent_id(self, parent_id: str) -> "MessageBuilder":
        """设置父消息 ID

        Args:
            parent_id: 父消息 ID

        Returns:
            MessageBuilder: 消息构建器
        """
        self._metadata["parent_id"] = parent_id
        return self

    def build(self) -> AgentMessage:
        """构建消息

        Returns:
            AgentMessage: 消息对象
        """
        if self._message_type is None:
            raise ValueError("消息类型未设置")
        if not self._sender:
            raise ValueError("发送者未设置")
        if not self._receiver:
            raise ValueError("接收者未设置")
        if self._content is None:
            raise ValueError("消息内容未设置")

        return AgentMessage(
            message_type=self._message_type,
            sender=self._sender,
            receiver=self._receiver,
            content=self._content,
            priority=self._priority,
            metadata=self._metadata,
        )


class Protocol:
    """通信协议常量"""

    # Agent 名称
    DECISION_AGENT = "decision"
    REVIEW_AGENT = "review"
    ARBITRATE_AGENT = "arbitrate"
    COORDINATOR = "coordinator"

    # 超时和重试
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30

    # 消息版本
    MESSAGE_VERSION = "1.0"

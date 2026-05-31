from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.gateway.base_adapter import BaseAdapter, MessageEvent, PlatformAdapter

logger = logging.getLogger(__name__)


class ApiAdapter(BaseAdapter):
    """API 接入层适配器。

    处理来自 HTTP API 的消息，提供基本的校验和响应能力。
    platform_name 固定为 "api"。
    """

    @property
    def platform_name(self) -> str:
        """获取平台名称。"""
        return "api"

    async def send_message(
        self, user_id: str, message: str, conversation_id: str = ""
    ) -> str:
        """发送消息，在 API 模式下返回模拟 message_id。

        Args:
            user_id: 目标用户 ID
            message: 消息文本
            conversation_id: 会话 ID

        Returns:
            str: 消息 ID
        """
        message_id = str(uuid.uuid4())
        logger.info(
            "[api] send_message: user=%s conv=%s msg_id=%s",
            user_id,
            conversation_id,
            message_id,
        )
        return message_id

    async def validate_webhook(self, data: dict[str, Any]) -> bool:
        """验证 API 请求的合法性，检查 API Key。

        Args:
            data: 请求数据，应包含 "api_key" 字段

        Returns:
            bool: API Key 存在且非空时返回 True
        """
        api_key = data.get("api_key", "")
        if not api_key:
            logger.warning("[api] validate_webhook 失败: 缺少 api_key")
            return False
        logger.info("[api] validate_webhook 通过")
        return True

    async def parse_webhook(
        self, data: dict[str, Any]
    ) -> MessageEvent | None:
        """解析 API 请求体为 MessageEvent。

        从 data 中提取 message、user_id、conversation_id 等字段，
        构造成 MessageEvent 返回。

        Args:
            data: API 请求数据字典

        Returns:
            MessageEvent | None: 解析成功后的事件对象
        """
        message = data.get("message", "")
        if not message:
            logger.warning("[api] parse_webhook 失败: 消息内容为空")
            return None

        return MessageEvent(
            platform=self.platform_name,
            user_id=data.get("user_id", "api_user"),
            message=message,
            message_type=data.get("message_type", "text"),
            conversation_id=data.get("conversation_id", ""),
            raw_data=data,
            metadata={
                "source": "api",
                "api_key_present": bool(data.get("api_key")),
            },
        )


def create_api_response(
    success: bool,
    data: Any = None,
    error: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """创建标准化的 API 响应对象。

    Args:
        success: 请求是否成功
        data: 响应数据
        error: 错误信息（失败时）
        message_id: 消息 ID

    Returns:
        dict: 标准化的响应字典
    """
    response: dict[str, Any] = {"success": success}
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
    if message_id is not None:
        response["message_id"] = message_id
    return response


def validate_api_request(body: str | bytes | None) -> dict[str, Any] | None:
    """验证 API 请求体的格式和完整性。

    检查请求体是否为合法的 JSON，以及是否包含必要字段。

    Args:
        body: 原始请求体

    Returns:
        dict | None: 解析成功返回字典，失败返回 None
    """
    if not body:
        logger.warning("[api] validate_api_request 失败: 请求体为空")
        return None

    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("[api] validate_api_request 失败: JSON 解析错误 %s", e)
        return None

    if "message" not in data:
        logger.warning("[api] validate_api_request 失败: 缺少 message 字段")
        return None

    return data
from __future__ import annotations

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from src.gateway.base_adapter import MessageEvent, PlatformAdapter

logger = logging.getLogger(__name__)

_WECHAT_WORK_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WechatWorkAdapter(PlatformAdapter):
    """企业微信适配器。

    实现企业微信消息的收发、Webhook 验签和消息解析。
    使用 httpx 异步 HTTP 客户端调用企业微信 API。
    """

    def __init__(
        self,
        corpid: str = "",
        corpsecret: str = "",
        token: str = "",
        encoding_aes_key: str = "",
        agent_id: int = 0,
    ) -> None:
        """初始化企业微信适配器。

        Args:
            corpid: 企业 ID
            corpsecret: 应用 Secret
            token: Webhook 验证 Token
            encoding_aes_key: 消息加解密密钥
            agent_id: 应用 Agent ID
        """
        self._corpid = corpid
        self._corpsecret = corpsecret
        self._token = token
        self._encoding_aes_key = encoding_aes_key
        self._agent_id = agent_id
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        logger.info("WechatWorkAdapter 初始化完成")

    @property
    def platform_name(self) -> str:
        """获取平台名称。"""
        return "wechat_work"

    async def get_access_token(self, corpid: str = "", corpsecret: str = "") -> str:
        """获取企业微信 access_token（带缓存）。

        Token 有效期为 7200 秒，缓存在内存中并在过期后自动刷新。

        Args:
            corpid: 企业 ID，为空时使用初始化值
            corpsecret: 应用 Secret，为空时使用初始化值

        Returns:
            str: access_token

        Raises:
            RuntimeError: 获取 access_token 失败时抛出
        """
        cid = corpid or self._corpid
        secret = corpsecret or self._corpsecret

        if not cid or not secret:
            raise RuntimeError("企业微信配置缺失: corpid 和 corpsecret 必须提供")

        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{_WECHAT_WORK_API_BASE}/gettoken"
        params = {"corpid": cid, "corpsecret": secret}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        errcode = data.get("errcode", -1)
        if errcode != 0:
            errmsg = data.get("errmsg", "未知错误")
            raise RuntimeError(f"获取 access_token 失败: errcode={errcode} errmsg={errmsg}")

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in - 60
        logger.info("企业微信 access_token 刷新成功，有效期 %d 秒", expires_in)
        return self._access_token

    async def send_message(
        self, user_id: str, message: str, conversation_id: str = ""
    ) -> str:
        """发送文本消息到企业微信用户。

        Args:
            user_id: 目标用户 ID（企业微信 UserID）
            message: 消息文本
            conversation_id: 会话 ID

        Returns:
            str: 消息 ID（企业微信的 msgid）
        """
        token = await self.get_access_token()
        url = f"{_WECHAT_WORK_API_BASE}/message/send?access_token={token}"

        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self._agent_id,
            "text": {"content": message},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        errcode = data.get("errcode", -1)
        if errcode != 0:
            errmsg = data.get("errmsg", "未知错误")
            logger.error(
                "企业微信消息发送失败: user=%s errcode=%d errmsg=%s",
                user_id,
                errcode,
                errmsg,
            )
            return ""

        msg_id = data.get("msgid", "")
        logger.info("企业微信消息发送成功: user=%s msg_id=%s", user_id, msg_id)
        return msg_id

    async def send_rich_message(
        self,
        user_id: str,
        content_type: str,
        content: dict[str, Any],
        conversation_id: str = "",
    ) -> str:
        """发送富文本消息到企业微信。

        支持的内容类型包括: markdown、news（图文）、textcard（卡片消息）。

        Args:
            user_id: 目标用户 ID
            content_type: 内容类型（markdown, news, textcard）
            content: 内容数据
            conversation_id: 会话 ID

        Returns:
            str: 消息 ID
        """
        token = await self.get_access_token()
        url = f"{_WECHAT_WORK_API_BASE}/message/send?access_token={token}"

        payload: dict[str, Any] = {
            "touser": user_id,
            "msgtype": content_type,
            "agentid": self._agent_id,
        }

        if content_type == "markdown":
            payload["markdown"] = {"content": content.get("content", "")}
        elif content_type == "news":
            payload["news"] = {
                "articles": content.get("articles", [])
            }
        elif content_type == "textcard":
            payload["textcard"] = {
                "title": content.get("title", ""),
                "description": content.get("description", ""),
                "url": content.get("url", ""),
            }
        else:
            logger.warning("不支持的富文本类型: %s，回退为纯文本", content_type)
            return await self.send_message(
                user_id, content.get("content", str(content)), conversation_id
            )

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        errcode = data.get("errcode", -1)
        if errcode != 0:
            errmsg = data.get("errmsg", "未知错误")
            logger.error(
                "企业微信富文本消息发送失败: user=%s type=%s errcode=%d errmsg=%s",
                user_id,
                content_type,
                errcode,
                errmsg,
            )
            return ""

        msg_id = data.get("msgid", "")
        logger.info(
            "企业微信富文本消息发送成功: user=%s type=%s msg_id=%s",
            user_id,
            content_type,
            msg_id,
        )
        return msg_id

    async def edit_message(
        self, conversation_id: str, message_id: str, new_content: str
    ) -> bool:
        """编辑企业微信消息（仅支持更新卡片消息）。

        Args:
            conversation_id: 会话 ID
            message_id: 要编辑的消息 ID
            new_content: 新的消息内容

        Returns:
            bool: 编辑是否成功
        """
        token = await self.get_access_token()
        url = f"{_WECHAT_WORK_API_BASE}/message/update?access_token={token}"

        payload = {
            "msgid": message_id,
            "textcard": {
                "title": "消息已更新",
                "description": new_content,
                "url": "",
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        success = data.get("errcode", -1) == 0
        if not success:
            logger.warning(
                "企业微信消息编辑失败: msg_id=%s errcode=%d",
                message_id,
                data.get("errcode"),
            )
        return success

    async def delete_message(
        self, conversation_id: str, message_id: str
    ) -> bool:
        """删除企业微信消息（企业微信 API 不支持删除消息）。

        Args:
            conversation_id: 会话 ID
            message_id: 要删除的消息 ID

        Returns:
            bool: 始终返回 False
        """
        logger.warning(
            "企业微信不支持删除消息: conv=%s msg_id=%s",
            conversation_id,
            message_id,
        )
        return False

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取企业微信用户信息。

        Args:
            user_id: 企业微信 UserID

        Returns:
            dict: 用户信息字典
        """
        token = await self.get_access_token()
        url = f"{_WECHAT_WORK_API_BASE}/user/get"
        params = {"access_token": token, "userid": user_id}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        errcode = data.get("errcode", -1)
        if errcode != 0:
            logger.warning(
                "获取企业微信用户信息失败: user=%s errcode=%d",
                user_id,
                errcode,
            )
            return {"user_id": user_id, "platform": "wechat_work"}

        return {
            "user_id": data.get("userid", user_id),
            "platform": "wechat_work",
            "name": data.get("name", ""),
            "mobile": data.get("mobile", ""),
            "department": data.get("department", []),
            "position": data.get("position", ""),
            "email": data.get("email", ""),
        }

    async def validate_webhook(self, data: dict[str, Any]) -> bool:
        """验证企业微信回调请求的签名。

        使用 SHA-1 签名验证机制，检查 msg_signature 是否合法。

        Args:
            data: 回调请求数据，应包含 msg_signature、timestamp、nonce、echostr

        Returns:
            bool: 签名验证是否通过
        """
        msg_signature = data.get("msg_signature", "")
        timestamp = data.get("timestamp", "")
        nonce = data.get("nonce", "")
        echostr = data.get("echostr", "")

        if not self._token:
            logger.warning("企业微信 Token 未配置，跳过签名验证")
            return True

        sort_list = sorted([self._token, str(timestamp), str(nonce), echostr])
        raw = "".join(sort_list)
        signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()

        if signature != msg_signature:
            logger.warning(
                "企业微信签名验证失败: expected=%s got=%s",
                signature,
                msg_signature,
            )
            return False

        logger.info("企业微信签名验证通过")
        return True

    async def parse_webhook(
        self, data: dict[str, Any]
    ) -> MessageEvent | None:
        """解析企业微信回调 XML 消息为 MessageEvent。

        支持文本消息、图片消息、语音消息等类型的解析。

        Args:
            data: 回调请求数据，应包含 XML 格式的消息体

        Returns:
            MessageEvent | None: 解析成功后的事件对象
        """
        xml_str = data.get("xml", "") or data.get("echostr", "")
        if not xml_str:
            logger.warning("企业微信 webhook 数据中缺少 XML 内容")
            return None

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            logger.warning("企业微信 XML 解析失败: %s", e)
            return None

        msg_type = root.findtext("MsgType", "text")
        content_elem = root.find("Content")
        content = content_elem.text if content_elem is not None else ""

        if msg_type == "image":
            content = "[图片消息]"
        elif msg_type == "voice":
            content = "[语音消息]"
        elif msg_type == "video":
            content = "[视频消息]"
        elif msg_type == "location":
            content = f"[位置消息] {root.findtext('Label', '')}"
        elif msg_type == "event":
            event = root.findtext("Event", "")
            event_key = root.findtext("EventKey", "")
            content = f"[事件] {event}: {event_key}"

        return MessageEvent(
            platform=self.platform_name,
            user_id=root.findtext("FromUserName", "unknown"),
            message=content,
            message_type=msg_type,
            conversation_id=root.findtext("ToUserName", ""),
            timestamp=float(root.findtext("CreateTime", "0")),
            raw_data=data,
            metadata={
                "msg_id": root.findtext("MsgId", ""),
                "agent_id": root.findtext("AgentID", ""),
                "msg_type": msg_type,
            },
        )
from __future__ import annotations

import logging
from typing import Any

from src.config import GatewayConfig
from src.gateway.base_adapter import MessageEvent, PlatformAdapter

logger = logging.getLogger(__name__)


class Gateway:
    """网关主类，负责管理平台适配器注册表和消息路由。

    工作流程：
    1. 注册各平台适配器（register_adapter）
    2. 接收 MessageEvent 并路由到对应适配器（route_message）
    3. 支持广播消息到多个平台（broadcast）
    """

    def __init__(self, config: GatewayConfig) -> None:
        """初始化网关。

        Args:
            config: 网关配置，包含各平台开关等设置
        """
        self._config = config
        self._adapters: dict[str, PlatformAdapter] = {}
        self._running = False
        logger.info(
            "Gateway 初始化完成，平台配置: cli=%s api=%s wechat_work=%s",
            config.platforms.cli.enabled,
            config.platforms.api.enabled,
            config.platforms.wechat_work.enabled,
        )

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """注册平台适配器。

        Args:
            adapter: 实现了 PlatformAdapter 接口的适配器实例

        Raises:
            ValueError: 如果同名平台已注册
        """
        name = adapter.platform_name
        if name in self._adapters:
            raise ValueError(f"平台 '{name}' 的适配器已注册")
        self._adapters[name] = adapter
        logger.info("注册平台适配器: %s", name)

    def unregister_adapter(self, platform: str) -> None:
        """注销指定平台的适配器。

        Args:
            platform: 平台名称
        """
        removed = self._adapters.pop(platform, None)
        if removed is not None:
            logger.info("注销平台适配器: %s", platform)
        else:
            logger.warning("尝试注销不存在的平台适配器: %s", platform)

    def get_adapter(self, platform: str) -> PlatformAdapter | None:
        """获取指定平台的适配器。

        Args:
            platform: 平台名称

        Returns:
            PlatformAdapter | None: 适配器实例，未注册时返回 None
        """
        return self._adapters.get(platform)

    def list_adapters(self) -> list[str]:
        """列出所有已注册的平台名称。

        Returns:
            list[str]: 已注册的平台名称列表
        """
        return list(self._adapters.keys())

    def is_platform_enabled(self, platform: str) -> bool:
        """检查平台是否在配置中启用。

        Args:
            platform: 平台名称

        Returns:
            bool: 是否启用
        """
        platforms_cfg = self._config.platforms
        cfg = getattr(platforms_cfg, platform, None)
        if cfg is None:
            return False
        return bool(cfg.enabled)

    async def route_message(self, event: MessageEvent) -> str | None:
        """路由消息到对应的平台适配器进行处理。

        根据 event.platform 查找已注册的适配器，调用 handle_event
        并将结果通过适配器的 send_message 返回。

        Args:
            event: 消息事件对象

        Returns:
            str | None: 回复消息的 message_id，若路由失败返回 None
        """
        adapter = self.get_adapter(event.platform)
        if adapter is None:
            logger.warning(
                "找不到平台 '%s' 的适配器，消息丢弃: event_id=%s",
                event.platform,
                event.event_id,
            )
            return None

        if not self.is_platform_enabled(event.platform):
            logger.warning(
                "平台 '%s' 未启用，消息丢弃: event_id=%s",
                event.platform,
                event.event_id,
            )
            return None

        try:
            reply_text = await adapter.handle_event(event)
            if reply_text is None:
                return None

            message_id = await adapter.send_message(
                user_id=event.user_id,
                message=reply_text,
                conversation_id=event.conversation_id,
            )
            logger.info(
                "消息路由成功: platform=%s event_id=%s msg_id=%s",
                event.platform,
                event.event_id,
                message_id,
            )
            return message_id
        except Exception:
            logger.exception(
                "消息路由失败: platform=%s event_id=%s",
                event.platform,
                event.event_id,
            )
            return None

    async def broadcast(
        self, message: str, platforms: list[str] | None = None
    ) -> dict[str, str]:
        """广播消息到多个平台。

        Args:
            message: 要广播的消息内容
            platforms: 目标平台列表，为 None 时广播到所有已注册平台

        Returns:
            dict[str, str]: 平台名称到 message_id 的映射
        """
        targets = platforms if platforms is not None else self.list_adapters()
        results: dict[str, str] = {}

        for platform_name in targets:
            adapter = self.get_adapter(platform_name)
            if adapter is None:
                logger.warning("广播跳过: 平台 '%s' 未注册", platform_name)
                continue

            if not self.is_platform_enabled(platform_name):
                logger.warning("广播跳过: 平台 '%s' 未启用", platform_name)
                continue

            try:
                message_id = await adapter.send_message(
                    user_id="broadcast",
                    message=message,
                    conversation_id="",
                )
                results[platform_name] = message_id
            except Exception:
                logger.exception("广播失败: platform=%s", platform_name)
                results[platform_name] = ""

        logger.info("广播完成: targets=%s results=%s", targets, results)
        return results

    async def start(self) -> None:
        """启动网关。"""
        self._running = True
        logger.info(
            "网关启动，已注册适配器: %s", self.list_adapters()
        )

    async def stop(self) -> None:
        """关闭网关，清理适配器资源。"""
        self._running = False
        self._adapters.clear()
        logger.info("网关已关闭")
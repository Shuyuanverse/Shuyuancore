# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""LLM Provider 工厂函数。

提供全局函数获取配置好的模型提供者实例。
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import get_settings
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_provider_cache: Optional[IModelProvider] = None


def get_model_provider() -> IModelProvider:
    """获取模型提供者实例。

    使用单例模式缓存 provider 实例，避免重复创建。

    Returns:
        IModelProvider: 模型提供者实例

    Raises:
        RuntimeError: 当无法创建提供者实例时
    """
    global _provider_cache

    if _provider_cache is not None:
        return _provider_cache

    cfg = get_settings()

    # 根据配置选择提供者
    # 默认使用 DashScope
    try:
        from src.models.dashscope import DashScopeProvider

        provider: IModelProvider = DashScopeProvider(
            api_key=cfg.dashscope.api_key,
            base_url=cfg.dashscope.base_url,
        )

        logger.info("Initialized DashScope provider")
        _provider_cache = provider
        return provider

    except ImportError:
        logger.warning("DashScope not available, trying DeepSeek")

        try:
            from src.models.deepseek import DeepSeekProvider

            provider = DeepSeekProvider(
                api_key=cfg.deepseek.api_key,
                base_url=cfg.deepseek.base_url,
            )

            logger.info("Initialized DeepSeek provider")
            _provider_cache = provider
            return provider

        except ImportError:
            logger.error("No LLM provider available")
            raise RuntimeError("No LLM provider available")


def reset_provider_cache() -> None:
    """重置 provider 缓存。

    用于测试场景，允许重新初始化 provider。
    """
    global _provider_cache
    _provider_cache = None
    logger.debug("Provider cache reset")

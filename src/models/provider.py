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
    providers_cfg = cfg.models.providers

    if not providers_cfg:
        raise RuntimeError("No model providers configured")

    for provider_name, provider_cfg in providers_cfg.items():
        if not provider_cfg.api_key and provider_name not in ("ollama",):
            continue
        if not provider_cfg.model and not provider_cfg.api_key:
            continue

        if provider_name == "dashscope":
            from src.models.dashscope import DashScopeProvider

            provider: IModelProvider = DashScopeProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                model=provider_cfg.model,
                embedding_model=provider_cfg.embedding_model,
            )
        elif provider_name == "deepseek":
            from src.models.deepseek import DeepSeekProvider

            provider = DeepSeekProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                model=provider_cfg.model,
            )
        elif provider_name == "ollama":
            from src.models.openai_compat import OllamaProvider

            provider = OllamaProvider(
                base_url=provider_cfg.base_url,
                model=provider_cfg.model,
            )
        else:
            from src.models.openai_compat import OpenAICompatProvider

            provider = OpenAICompatProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                model=provider_cfg.model,
            )

        logger.info("Initialized %s provider", provider_name)
        _provider_cache = provider
        return provider

    raise RuntimeError("No usable model provider found")


def reset_provider_cache() -> None:
    """重置 provider 缓存。

    用于测试场景，允许重新初始化 provider。
    """
    global _provider_cache
    _provider_cache = None
    logger.debug("Provider cache reset")

# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from src.config import get_settings
from src.models.interfaces import IModelProvider, ProviderRegistry

logger = logging.getLogger(__name__)

_provider_cache: IModelProvider | None = None


def get_model_provider(config: dict[str, Any] | None = None) -> IModelProvider:
    if _provider_cache is not None and config is None:
        return _provider_cache

    if config is not None:
        return create_provider(config.get("provider", ""), config)

    cfg = get_settings()
    providers_cfg = cfg.models.providers

    if not providers_cfg:
        raise RuntimeError("No model providers configured")

    for provider_name, provider_cfg in providers_cfg.items():
        if not provider_cfg.api_key and provider_name not in ("ollama",):
            continue
        if not provider_cfg.model and not provider_cfg.api_key:
            continue

        provider = create_provider(provider_name, provider_cfg.model_dump())
        _provider_cache = provider
        return provider

    raise RuntimeError("No usable model provider found")


def get_embedding_provider(config: dict[str, Any] | None = None) -> IModelProvider | None:
    if config is not None:
        provider_name = config.get("provider", "")
        return create_provider(provider_name, config)

    cfg = get_settings()
    providers_cfg = cfg.models.providers

    if "dashscope" in providers_cfg:
        return create_provider("dashscope", providers_cfg["dashscope"].model_dump())

    for provider_name, provider_cfg in providers_cfg.items():
        try:
            provider = create_provider(provider_name, provider_cfg.model_dump())
            return provider
        except Exception:
            continue

    return None


def list_available_providers() -> list[str]:
    cfg = get_settings()
    return list(cfg.models.providers.keys())


def create_provider(provider_name: str, config: dict[str, Any] | None = None) -> IModelProvider:
    resolved_name = provider_name.lower().strip()

    cfg = config or {}
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model", "")
    embedding_model = cfg.get("embedding_model", "")

    if resolved_name == "dashscope":
        from src.models.dashscope import DashScopeProvider

        return DashScopeProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            embedding_model=embedding_model,
        )

    if resolved_name == "deepseek":
        from src.models.deepseek import DeepSeekProvider

        return DeepSeekProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    if resolved_name == "ollama":
        from src.models.openai_compat import OllamaProvider

        return OllamaProvider(
            base_url=base_url,
            model=model,
        )

    from src.models.openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def reset_provider_cache() -> None:
    global _provider_cache
    _provider_cache = None
    logger.debug("Provider cache reset")
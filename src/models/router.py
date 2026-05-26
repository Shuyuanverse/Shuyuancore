from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from src.config import get_settings
from src.exceptions import ModelCallError, ModelSwitchError
from src.models.interfaces import (
    ChatResult,
    EmbeddingResult,
    HealthStatus,
    IModelProvider,
    ProviderRegistry,
)

_logger = logging.getLogger("shuyuancore.models.router")

_FAILOVER_RECOVER_SECONDS = 300
_FAILOVER_CONSECUTIVE_429_LIMIT = 3
_FAILOVER_RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}

_TASK_TYPES: list[str] = ["chat", "code", "math", "embedding", "tool", "review"]


@dataclass
class FailoverState:
    primary_failures: int = 0
    consecutive_429_count: int = 0
    on_fallback: bool = False
    switched_at: float = 0.0
    last_error: str = ""


@dataclass
class RouteRule:
    task_type: str
    primary_provider: str
    primary_model: str
    fallback_provider: str
    fallback_model: str


def _parse_model_spec(spec: str) -> tuple[str, str]:
    parts = spec.split("/", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]


class Router:

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self._registry = registry or ProviderRegistry()
        self._failover_states: dict[str, FailoverState] = {}
        self._rules: list[RouteRule] = []
        self._current_models: dict[str, str] = {}
        self._reload_config()

    def set_registry(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def _reload_config(self) -> None:
        settings = get_settings()
        cfg = settings.models

        self._rules = []
        self._current_models = {}

        for task_type in _TASK_TYPES:
            spec = getattr(cfg.routing, task_type, "")
            provider_name, model_name = _parse_model_spec(spec)

            if not provider_name:
                provider_name = _parse_model_spec(cfg.default)[0]

            self._current_models[task_type] = spec or cfg.default

            fallback_provider = ""
            fallback_model = ""

            if provider_name == "dashscope" and "deepseek" in cfg.providers:
                deepseek_cfg = cfg.providers["deepseek"]
                fallback_model_name = deepseek_cfg.model or "deepseek-chat"
                fallback_provider = "deepseek"
                fallback_model = fallback_model_name
            elif provider_name == "deepseek" and "dashscope" in cfg.providers:
                dashscope_cfg = cfg.providers["dashscope"]
                fallback_model_name = dashscope_cfg.model or "qwen-max"
                fallback_provider = "dashscope"
                fallback_model = fallback_model_name

            self._rules.append(
                RouteRule(
                    task_type=task_type,
                    primary_provider=provider_name,
                    primary_model=model_name,
                    fallback_provider=fallback_provider,
                    fallback_model=fallback_model,
                )
            )

            if task_type not in self._failover_states:
                self._failover_states[task_type] = FailoverState()

    def _get_provider(self, provider_name: str) -> IModelProvider:
        provider = self._registry.get(provider_name)
        if provider is None:
            raise ModelSwitchError(
                message=(
                    f"模型提供者 '{provider_name}' 未注册"
                    f" / Provider '{provider_name}' not registered"
                ),
            )
        return provider

    def _get_current_spec(self, task_type: str) -> str:
        return self._current_models.get(task_type, "")

    async def chat(
        self,
        history: list[dict[str, Any]],
        task_type: str = "chat",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        return await self._call_with_failover(
            "chat", task_type, history, temperature, max_tokens
        )

    async def embed(
        self,
        texts: list[str],
        task_type: str = "embedding",
    ) -> EmbeddingResult:
        rule = self._resolve(task_type)
        provider = self._get_provider(rule.primary_provider)
        try:
            return await provider.embed(texts, model=rule.primary_model)
        except NotImplementedError:
            raise ModelCallError(
                message=(
                    f"Provider '{rule.primary_provider}' 不支持 embedding"
                    f" / Provider '{rule.primary_provider}' does not support embedding"
                ),
            )

    def resolve(self, task_type: str) -> tuple[IModelProvider, str]:
        rule = self._resolve(task_type)
        provider = self._get_provider(rule.primary_provider)
        return provider, rule.primary_model

    def _resolve(self, task_type: str) -> RouteRule:
        for rule in self._rules:
            if rule.task_type == task_type:
                return rule
        default_chat = self._rules[0] if self._rules else RouteRule(
            task_type=task_type,
            primary_provider="",
            primary_model="",
            fallback_provider="",
            fallback_model="",
        )
        return default_chat

    async def _call_with_failover(
        self,
        call_type: str,
        task_type: str,
        history: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        rule = self._resolve(task_type)
        state = self._failover_states.setdefault(task_type, FailoverState())

        self._check_recover(state, rule)

        if state.on_fallback:
            provider = self._get_provider(rule.fallback_provider)
            model = rule.fallback_model
            provider_name = rule.fallback_provider
        else:
            provider = self._get_provider(rule.primary_provider)
            model = rule.primary_model
            provider_name = rule.primary_provider

        try:
            result = await provider.chat(
                history=history,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            state.primary_failures = 0
            state.consecutive_429_count = 0
            return result

        except Exception as exc:
            state.primary_failures += 1
            error_str = str(exc)

            is_rate_limited = "429" in error_str or "rate_limit" in error_str.lower()
            if is_rate_limited:
                state.consecutive_429_count += 1
            else:
                state.consecutive_429_count = 0

            should_failover = (
                state.primary_failures >= 1
                and rule.fallback_provider
                and rule.fallback_model
            )

            if state.consecutive_429_count >= _FAILOVER_CONSECUTIVE_429_LIMIT:
                should_failover = True

            if should_failover and not state.on_fallback:
                state.on_fallback = True
                state.switched_at = time.monotonic()
                state.last_error = error_str
                _logger.warning(
                    "failover_triggered task_type=%s primary=%s fallback=%s error=%s",
                    task_type,
                    provider_name,
                    rule.fallback_provider,
                    error_str,
                )

                fallback_provider = self._get_provider(rule.fallback_provider)
                try:
                    result = await fallback_provider.chat(
                        history=history,
                        model=rule.fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return result
                except Exception as fallback_exc:
                    raise ModelCallError(
                        message=(
                            f"主模型 ({provider_name}/{model}) 和备选模型"
                            f" ({rule.fallback_provider}/{rule.fallback_model}) 均失败"
                            f" / Both primary ({provider_name}/{model}) and fallback"
                            f" ({rule.fallback_provider}/{rule.fallback_model}) failed"
                        ),
                        detail={
                            "primary_error": error_str,
                            "fallback_error": str(fallback_exc),
                            "task_type": task_type,
                        },
                    ) from fallback_exc

            if state.on_fallback:
                raise ModelCallError(
                    message=(
                        f"备选模型 ({rule.fallback_provider}/{rule.fallback_model}) 调用失败"
                        f" / Fallback model ({rule.fallback_provider}/{rule.fallback_model}) failed"
                    ),
                    detail={"error": error_str, "task_type": task_type},
                ) from exc

            raise ModelCallError(
                message=(
                    f"模型调用失败 ({provider_name}/{model})"
                    f" / Model call failed ({provider_name}/{model})"
                ),
                detail={"error": error_str, "task_type": task_type},
            ) from exc

    def _check_recover(self, state: FailoverState, rule: RouteRule) -> None:
        if not state.on_fallback:
            return
        elapsed = time.monotonic() - state.switched_at
        if elapsed >= _FAILOVER_RECOVER_SECONDS:
            state.on_fallback = False
            state.primary_failures = 0
            state.consecutive_429_count = 0
            _logger.info(
                "failover_recovered primary=%s fallback=%s elapsed=%ds",
                rule.primary_provider,
                rule.fallback_provider,
                int(elapsed),
            )

    async def check_health(self) -> dict[str, HealthStatus]:
        return await self._registry.check_all()

    def get_current_models(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for rule in self._rules:
            result[rule.task_type] = self._get_current_spec(rule.task_type)
        return result

    def switch_model(self, role: str, model_spec: str) -> dict[str, Any]:
        valid_roles = _TASK_TYPES + ["main", "tool", "review"]
        role_map: dict[str, str] = {
            "main": "chat",
            "tool": "tool",
            "review": "review",
        }
        target_role = role_map.get(role, role)

        if target_role not in _TASK_TYPES:
            raise ModelSwitchError(
                message=(
                    f"无效的角色 '{role}'，有效值: {', '.join(valid_roles)}"
                    f" / Invalid role '{role}', valid: {', '.join(valid_roles)}"
                ),
            )

        provider_name, model_name = _parse_model_spec(model_spec)
        if not provider_name:
            raise ModelSwitchError(
                message=(
                    f"模型规格格式无效 '{model_spec}'，应为 'provider/model'"
                    f" / Invalid model spec '{model_spec}', expected 'provider/model'"
                ),
            )

        provider = self._registry.get(provider_name)
        if provider is None:
            raise ModelSwitchError(
                message=(
                    f"模型提供者 '{provider_name}' 未注册"
                    f" / Provider '{provider_name}' not registered"
                ),
            )

        for i, rule in enumerate(self._rules):
            if rule.task_type == target_role:
                self._rules[i] = RouteRule(
                    task_type=target_role,
                    primary_provider=provider_name,
                    primary_model=model_name,
                    fallback_provider=rule.fallback_provider,
                    fallback_model=rule.fallback_model,
                )
                self._current_models[target_role] = model_spec
                break

        state = self._failover_states.get(target_role)
        if state:
            state.on_fallback = False
            state.primary_failures = 0
            state.consecutive_429_count = 0

        _logger.info(
            "model_switched role=%s model_spec=%s",
            target_role,
            model_spec,
        )

        return {
            "role": target_role,
            "model": model_spec,
        }

    def get_routing_rules(self) -> list[dict[str, str]]:
        return [
            {
                "task_type": rule.task_type,
                "model": self._get_current_spec(rule.task_type),
            }
            for rule in self._rules
        ]

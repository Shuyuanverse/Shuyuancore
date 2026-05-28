from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class ChatResult:
    content: str
    tokens_used: int = 0
    model_used: str = ""
    finish_reason: str = "stop"


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model_used: str = ""
    dimensions: int = 0


@dataclass
class HealthStatus:
    ok: bool = False
    latency_ms: int = 0
    error: str | None = None


@dataclass
class ChatStreamEvent:
    type: str = "content"
    content: str = ""
    tool_name: str | None = None
    tool_params: str | None = None
    tool_result: str | None = None
    tokens_used: int = 0


class IModelProvider(ABC):

    @abstractmethod
    async def chat(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        yield ChatStreamEvent()  # pragma: no cover

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        ...

    @abstractmethod
    async def check_health(self) -> HealthStatus:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class ProviderRegistry:

    def __init__(self) -> None:
        self._providers: dict[str, IModelProvider] = {}

    def register(self, name: str, provider: IModelProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> IModelProvider | None:
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    async def check_all(self) -> dict[str, HealthStatus]:
        results: dict[str, HealthStatus] = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.check_health()
            except Exception as exc:
                results[name] = HealthStatus(ok=False, error=str(exc))
        return results

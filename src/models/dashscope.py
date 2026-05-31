from __future__ import annotations

import time
from typing import Any, AsyncIterator

from src.models._client import HttpxClient
from src.models.interfaces import (
    ChatResult,
    ChatStreamEvent,
    EmbeddingResult,
    HealthStatus,
    IModelProvider,
)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-max"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-v2"
_EMBEDDING_DIMENSIONS = 1536


class DashScopeProvider(IModelProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._embedding_model = embedding_model
        self._client = HttpxClient(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def name(self) -> str:
        return "dashscope"

    async def chat(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": history,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response = await self._client.post("/chat/completions", payload)
        data: dict[str, Any] = response.json()

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "stop")
        usage = data.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)

        return ChatResult(
            content=content,
            tokens_used=tokens_used,
            model_used=data.get("model", model or self._model),
            finish_reason=finish_reason,
        )

    async def chat_stream(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": history,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        url = f"{self._base_url}/chat/completions"

        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._client._timeout, connect=self._client._connect_timeout),
        ) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk_data_str = line[6:].strip()
                    if not chunk_data_str or chunk_data_str == "[DONE]":
                        continue
                    import json

                    chunk: dict[str, Any] = json.loads(chunk_data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        yield ChatStreamEvent(
                            type="content",
                            content=delta["content"],
                        )
                    finish = chunk.get("choices", [{}])[0].get("finish_reason")
                    if finish:
                        usage = chunk.get("usage", {})
                        yield ChatStreamEvent(
                            type="done",
                            tokens_used=usage.get("total_tokens", 0),
                        )

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        payload: dict[str, Any] = {
            "model": model or self._embedding_model,
            "input": texts,
        }
        response = await self._client.post("/embeddings", payload)
        data: dict[str, Any] = response.json()

        vectors: list[list[float]] = []
        for item in data.get("data", []):
            vectors.append(item["embedding"])

        return EmbeddingResult(
            vectors=vectors,
            model_used=data.get("model", model or self._embedding_model),
            dimensions=_EMBEDDING_DIMENSIONS,
        )

    async def check_health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            _ = await self.chat(
                history=[{"role": "user", "content": "ping"}],
                model=self._model,
                max_tokens=1,
            )
            latency = int((time.monotonic() - start) * 1000)
            return HealthStatus(ok=True, latency_ms=latency)
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            return HealthStatus(ok=False, latency_ms=latency, error=str(exc))

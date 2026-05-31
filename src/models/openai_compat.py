from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"


class OpenAICompatProvider(IModelProvider):
    def __init__(
        self,
        api_key: str = "",
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        embedding_model: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        if not api_key:
            logger.warning(
                "OpenAI API key is empty. Set OPENAI_API_KEY or pass api_key to the constructor. / "
                "OpenAI API Key 为空，请设置 OPENAI_API_KEY 或传入 api_key 参数。"
            )
        self._base_url = base_url
        self._model = model
        self._embedding_model = embedding_model
        self._client = HttpxClient(
            base_url=base_url,
            api_key=api_key or None,
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def name(self) -> str:
        return "openai_compat"

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
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
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
        if not self._embedding_model:
            raise NotImplementedError("Embedding model not configured for this provider")
        payload: dict[str, Any] = {
            "model": model or self._embedding_model,
            "input": texts,
        }
        response = await self._client.post("/embeddings", payload)
        data: dict[str, Any] = response.json()

        vectors: list[list[float]] = []
        for item in data.get("data", []):
            vectors.append(item["embedding"])

        dimensions = len(vectors[0]) if vectors else 0
        return EmbeddingResult(
            vectors=vectors,
            model_used=data.get("model", model or self._embedding_model),
            dimensions=dimensions,
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
        except NotImplementedError:
            return HealthStatus(ok=False, error="embedding_not_supported")
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            return HealthStatus(ok=False, latency_ms=latency, error=str(exc))


class OllamaProvider(OpenAICompatProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            api_key="",
            base_url=base_url.rstrip("/v1"),
            model=model,
            embedding_model=None,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

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
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature / 2.0
        ollama_model = model or self._model
        ollama_url = f"{self._base_url}/api/chat"

        headers: dict[str, str] = {"Content-Type": "application/json"}

        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._client._timeout, connect=self._client._connect_timeout),
        ) as client:
            response = await client.post(ollama_url, headers=headers, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        return ChatResult(
            content=data.get("message", {}).get("content", ""),
            tokens_used=0,
            model_used=data.get("model", ollama_model),
            finish_reason="stop",
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
            payload["temperature"] = temperature / 2.0
        ollama_url = f"{self._base_url}/api/chat"

        headers: dict[str, str] = {"Content-Type": "application/json"}

        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._client._timeout, connect=self._client._connect_timeout),
        ) as client:
            async with client.stream("POST", ollama_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    import json

                    chunk: dict[str, Any] = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        yield ChatStreamEvent(
                            type="content",
                            content=chunk["message"]["content"],
                        )
                    if chunk.get("done"):
                        yield ChatStreamEvent(
                            type="done",
                            tokens_used=0,
                        )

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> EmbeddingResult:
        ollama_model = model or self._model
        ollama_url = f"{self._base_url}/api/embed"

        payload: dict[str, Any] = {
            "model": ollama_model,
            "input": texts,
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}

        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._client._timeout, connect=self._client._connect_timeout),
        ) as client:
            response = await client.post(ollama_url, headers=headers, json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        vectors: list[list[float]] = data.get("embeddings", [])
        dimensions = len(vectors[0]) if vectors else 0
        return EmbeddingResult(
            vectors=vectors,
            model_used=data.get("model", ollama_model),
            dimensions=dimensions,
        )

    async def check_health(self) -> HealthStatus:
        import httpx

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=3.0),
            ) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                latency = int((time.monotonic() - start) * 1000)
                return HealthStatus(ok=True, latency_ms=latency)
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            return HealthStatus(ok=False, latency_ms=latency, error=str(exc))

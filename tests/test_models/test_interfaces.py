from __future__ import annotations

from src.models.interfaces import (
    ChatResult,
    ChatStreamEvent,
    EmbeddingResult,
    HealthStatus,
    ProviderRegistry,
)


class TestChatResult:

    def test_default_values(self) -> None:
        result = ChatResult(content="hello")
        assert result.content == "hello"
        assert result.tokens_used == 0
        assert result.model_used == ""
        assert result.finish_reason == "stop"

    def test_full_construction(self) -> None:
        result = ChatResult(
            content="hello",
            tokens_used=42,
            model_used="gpt-4",
            finish_reason="length",
        )
        assert result.content == "hello"
        assert result.tokens_used == 42
        assert result.model_used == "gpt-4"
        assert result.finish_reason == "length"


class TestEmbeddingResult:

    def test_default_values(self) -> None:
        result = EmbeddingResult(vectors=[[0.1, 0.2]])
        assert result.vectors == [[0.1, 0.2]]
        assert result.model_used == ""
        assert result.dimensions == 0

    def test_full_construction(self) -> None:
        result = EmbeddingResult(
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            model_used="text-embedding-v2",
            dimensions=2,
        )
        assert len(result.vectors) == 2
        assert result.model_used == "text-embedding-v2"
        assert result.dimensions == 2


class TestHealthStatus:

    def test_default_values(self) -> None:
        status = HealthStatus()
        assert status.ok is False
        assert status.latency_ms == 0
        assert status.error is None

    def test_ok_status(self) -> None:
        status = HealthStatus(ok=True, latency_ms=42)
        assert status.ok is True
        assert status.latency_ms == 42
        assert status.error is None

    def test_error_status(self) -> None:
        status = HealthStatus(ok=False, error="connection refused")
        assert status.ok is False
        assert status.error == "connection refused"


class TestChatStreamEvent:

    def test_content_event(self) -> None:
        event = ChatStreamEvent(type="content", content="hello")
        assert event.type == "content"
        assert event.content == "hello"
        assert event.tool_name is None

    def test_done_event(self) -> None:
        event = ChatStreamEvent(type="done", tokens_used=50)
        assert event.type == "done"
        assert event.tokens_used == 50


class TestProviderRegistry:

    def test_register_and_get(self) -> None:
        registry = ProviderRegistry()

        class MockProvider:
            name = "mock"

        provider = MockProvider()
        registry.register("mock", provider)  # type: ignore[arg-type]
        assert registry.get("mock") is provider
        assert registry.get("nonexistent") is None

    def test_list_providers(self) -> None:
        registry = ProviderRegistry()

        class MockProvider:
            name = "mock"

        registry.register("a", MockProvider())  # type: ignore[arg-type]
        registry.register("b", MockProvider())  # type: ignore[arg-type]
        providers = registry.list_providers()
        assert "a" in providers
        assert "b" in providers

    def test_check_all(self) -> None:
        registry = ProviderRegistry()

        class HealthyProvider:
            name = "healthy"

            async def check_health(self) -> HealthStatus:
                return HealthStatus(ok=True, latency_ms=10)

            async def chat(self, *args, **kwargs) -> ChatResult:
                return ChatResult(content="ok")

            async def embed(self, *args, **kwargs) -> EmbeddingResult:
                return EmbeddingResult(vectors=[])

        class UnhealthyProvider:
            name = "unhealthy"

            async def check_health(self) -> HealthStatus:
                return HealthStatus(ok=False, error="timeout")

            async def chat(self, *args, **kwargs) -> ChatResult:
                return ChatResult(content="ok")

            async def embed(self, *args, **kwargs) -> EmbeddingResult:
                return EmbeddingResult(vectors=[])


        registry.register("healthy", HealthyProvider())  # type: ignore[arg-type]
        registry.register("unhealthy", UnhealthyProvider())  # type: ignore[arg-type]

        import asyncio

        results = asyncio.run(registry.check_all())
        assert results["healthy"].ok is True
        assert results["unhealthy"].ok is False

    def test_check_all_with_exception(self) -> None:
        registry = ProviderRegistry()

        class BrokenProvider:
            name = "broken"

            async def check_health(self) -> HealthStatus:
                msg = "broken"
                raise RuntimeError(msg)

            async def chat(self, *args, **kwargs) -> ChatResult:
                return ChatResult(content="ok")

            async def embed(self, *args, **kwargs) -> EmbeddingResult:
                return EmbeddingResult(vectors=[])

        registry.register("broken", BrokenProvider())  # type: ignore[arg-type]

        import asyncio

        results = asyncio.run(registry.check_all())
        assert results["broken"].ok is False
        assert "broken" in (results["broken"].error or "")

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.exceptions import ModelCallError, ModelSwitchError
from src.models.interfaces import (
    ChatResult,
    EmbeddingResult,
    HealthStatus,
    IModelProvider,
    ProviderRegistry,
)
from src.models.router import Router


class MockProvider(IModelProvider):

    def __init__(self, name: str, ok: bool = True) -> None:
        self._name = name
        self._ok = ok
        self.chat_called_with: list = []
        self.embed_called_with: list = []

    @property
    def name(self) -> str:
        return self._name

    async def chat(
        self,
        history=None,
        model=None,
        temperature=None,
        max_tokens=None,
    ) -> ChatResult:
        self.chat_called_with.append((history, model))
        return ChatResult(
            content=f"response from {self._name}",
            tokens_used=10,
            model_used=model or f"{self._name}/model",
        )

    async def chat_stream(self, *args, **kwargs):
        yield  # pragma: no cover

    async def embed(self, texts=None, model=None) -> EmbeddingResult:
        self.embed_called_with.append((texts, model))
        return EmbeddingResult(
            vectors=[[0.1, 0.2]],
            model_used=model or f"{self._name}/embed",
            dimensions=2,
        )

    async def check_health(self) -> HealthStatus:
        if self._ok:
            return HealthStatus(ok=True, latency_ms=10)
        return HealthStatus(ok=False, error="mock_failure")


class FailingMockProvider(IModelProvider):

    def __init__(self, name: str, fail_count: int = 1) -> None:
        self._name = name
        self._fail_count = fail_count
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    async def chat(
        self,
        history=None,
        model=None,
        temperature=None,
        max_tokens=None,
    ) -> ChatResult:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            msg = f"{self._name} failed"
            raise ConnectionError(msg)
        return ChatResult(
            content="recovered",
            tokens_used=5,
            model_used=model or f"{self._name}/model",
        )

    async def chat_stream(self, *args, **kwargs):
        yield  # pragma: no cover

    async def embed(self, texts=None, model=None) -> EmbeddingResult:
        raise NotImplementedError

    async def check_health(self) -> HealthStatus:
        return HealthStatus(ok=True, latency_ms=10)


@pytest.fixture
def router() -> Router:
    with patch("src.models.router.get_settings") as mock_settings:
        settings = AsyncMock()
        settings.models.default = "dashscope/qwen-max"
        settings.models.embedding = "dashscope/text-embedding-v2"
        settings.models.embedding_dimensions = 1536

        routing = AsyncMock()
        routing.code = "deepseek/deepseek-chat"
        routing.chat = "dashscope/qwen-max"
        routing.math = "dashscope/qwen-max"
        routing.embedding = "dashscope/text-embedding-v2"
        routing.tool = "dashscope/qwen-turbo"
        routing.review = "deepseek/deepseek-chat"
        settings.models.routing = routing

        settings.models.providers = {
            "dashscope": AsyncMock(
                api_key="key1",
                base_url="https://dashscope/v1",
                model="qwen-max",
                embedding_model="text-embedding-v2",
            ),
            "deepseek": AsyncMock(
                api_key="key2",
                base_url="https://deepseek/v1",
                model="deepseek-chat",
                embedding_model="",
            ),
        }
        mock_settings.return_value = settings

        registry = ProviderRegistry()
        registry.register("dashscope", MockProvider("dashscope"))
        registry.register("deepseek", MockProvider("deepseek"))
        r = Router(registry=registry)
        return r


class TestRouter:

    def test_resolve_chat(self, router: Router) -> None:
        provider, model = router.resolve("chat")
        assert model == "qwen-max"
        assert provider.name == "dashscope"

    def test_resolve_code(self, router: Router) -> None:
        provider, model = router.resolve("code")
        assert model == "deepseek-chat"
        assert provider.name == "deepseek"

    def test_resolve_embedding(self, router: Router) -> None:
        provider, model = router.resolve("embedding")
        assert model == "text-embedding-v2"
        assert provider.name == "dashscope"

    def test_get_current_models(self, router: Router) -> None:
        models = router.get_current_models()
        assert models["chat"] == "dashscope/qwen-max"
        assert models["code"] == "deepseek/deepseek-chat"
        assert models["embedding"] == "dashscope/text-embedding-v2"

    def test_get_routing_rules(self, router: Router) -> None:
        rules = router.get_routing_rules()
        assert len(rules) == 6
        rule_map = {r["task_type"]: r["model"] for r in rules}
        assert rule_map["chat"] == "dashscope/qwen-max"
        assert rule_map["code"] == "deepseek/deepseek-chat"

    @pytest.mark.asyncio
    async def test_chat_success(self, router: Router) -> None:
        result = await router.chat(
            history=[{"role": "user", "content": "hello"}],
            task_type="chat",
        )
        assert result.content == "response from dashscope"
        assert result.tokens_used == 10

    @pytest.mark.asyncio
    async def test_embed_success(self, router: Router) -> None:
        result = await router.embed(texts=["hello"])
        assert len(result.vectors) == 1

    def test_switch_model_success(self, router: Router) -> None:
        result = router.switch_model("chat", "deepseek/deepseek-chat")
        assert result["role"] == "chat"
        assert result["model"] == "deepseek/deepseek-chat"

        provider, model = router.resolve("chat")
        assert model == "deepseek-chat"
        assert provider.name == "deepseek"

    def test_switch_model_invalid_role(self, router: Router) -> None:
        with pytest.raises(ModelSwitchError):
            router.switch_model("invalid_role", "dashscope/qwen-max")

    def test_switch_model_invalid_format(self, router: Router) -> None:
        with pytest.raises(ModelSwitchError):
            router.switch_model("chat", "no-slash")

    def test_switch_model_unregistered_provider(self, router: Router) -> None:
        with pytest.raises(ModelSwitchError):
            router.switch_model("chat", "unknown/model")

    @pytest.mark.asyncio
    async def test_check_health(self, router: Router) -> None:
        results = await router.check_health()
        assert "dashscope" in results
        assert "deepseek" in results
        assert results["dashscope"].ok is True
        assert results["deepseek"].ok is True


class TestRouterFailover:

    @pytest.mark.asyncio
    async def test_failover_on_error(self) -> None:
        with patch("src.models.router.get_settings") as mock_settings:
            settings = AsyncMock()
            settings.models.default = "dashscope/qwen-max"
            settings.models.embedding = "dashscope/text-embedding-v2"
            settings.models.embedding_dimensions = 1536

            routing = AsyncMock()
            routing.chat = "dashscope/qwen-max"
            routing.code = "deepseek/deepseek-chat"
            routing.math = "dashscope/qwen-max"
            routing.embedding = "dashscope/text-embedding-v2"
            routing.tool = "dashscope/qwen-turbo"
            routing.review = "deepseek/deepseek-chat"
            settings.models.routing = routing

            settings.models.providers = {
                "dashscope": AsyncMock(
                    api_key="k1",
                    base_url="https://d/v1",
                    model="qwen-max",
                    embedding_model="t",
                ),
                "deepseek": AsyncMock(
                    api_key="k2",
                    base_url="https://ds/v1",
                    model="deepseek-chat",
                    embedding_model="",
                ),
            }
            mock_settings.return_value = settings

            registry = ProviderRegistry()
            registry.register("dashscope", FailingMockProvider("dashscope", fail_count=2))
            registry.register("deepseek", MockProvider("deepseek"))
            router = Router(registry=registry)

            result = await router.chat(
                history=[{"role": "user", "content": "hi"}],
                task_type="chat",
            )
            assert "deepseek" in result.content

    @pytest.mark.asyncio
    async def test_both_fail(self) -> None:
        with patch("src.models.router.get_settings") as mock_settings:
            settings = AsyncMock()
            settings.models.default = "dashscope/qwen-max"
            settings.models.embedding = "dashscope/text-embedding-v2"
            settings.models.embedding_dimensions = 1536

            routing = AsyncMock()
            routing.chat = "dashscope/qwen-max"
            routing.code = "deepseek/deepseek-chat"
            routing.math = "dashscope/qwen-max"
            routing.embedding = "dashscope/text-embedding-v2"
            routing.tool = "dashscope/qwen-turbo"
            routing.review = "deepseek/deepseek-chat"
            settings.models.routing = routing

            settings.models.providers = {
                "dashscope": AsyncMock(
                    api_key="k1",
                    base_url="https://d/v1",
                    model="qwen-max",
                    embedding_model="t",
                ),
                "deepseek": AsyncMock(
                    api_key="k2",
                    base_url="https://ds/v1",
                    model="deepseek-chat",
                    embedding_model="",
                ),
            }
            mock_settings.return_value = settings

            registry = ProviderRegistry()
            registry.register("dashscope", FailingMockProvider("dashscope", fail_count=99))
            registry.register("deepseek", FailingMockProvider("deepseek", fail_count=99))
            router = Router(registry=registry)

            with pytest.raises(ModelCallError) as exc_info:
                await router.chat(
                    history=[{"role": "user", "content": "hi"}],
                    task_type="chat",
                )
            assert "均失败" in str(exc_info.value) or "Both" in str(exc_info.value)

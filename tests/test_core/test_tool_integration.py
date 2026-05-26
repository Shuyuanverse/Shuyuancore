from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from src.core.agent import Agent
from src.core.belief_store import BeliefStore
from src.core.interfaces import IToolRegistry, ToolSpec
from src.core.noop_implementations import MockToolRegistry
from src.core.reader import Reader
from src.models.interfaces import ChatStreamEvent, IModelProvider


class ToolCallProvider(IModelProvider):
    """Provider that simulates tool calls and then returns text."""

    def __init__(
        self,
        first_response: list[ChatStreamEvent],
        second_response: list[ChatStreamEvent] | None = None,
    ) -> None:
        self._responses = [first_response]
        if second_response is not None:
            self._responses.append(second_response)
        self._call_count = 0
        self._histories: list[list[dict[str, Any]]] = []

    @property
    def name(self) -> str:
        return "tool_mock"

    async def chat_stream(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self._histories.append(history)
        if self._call_count < len(self._responses):
            events = self._responses[self._call_count]
            self._call_count += 1
            for event in events:
                yield event
        else:
            yield ChatStreamEvent(type="done", tokens_used=0)

    async def chat(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        return type("obj", (), {"content": "", "tokens_used": 0})()

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> Any:
        return type("obj", (), {"vectors": [], "model_used": "", "dimensions": 0})()

    async def check_health(self) -> Any:
        return type("obj", (), {"ok": True, "latency_ms": 0, "error": None})()


class AlwaysToolProvider(IModelProvider):

    def __init__(self, max_calls: int = 5) -> None:
        self._max_calls = max_calls
        self._call_count = 0

    @property
    def name(self) -> str:
        return "always_tool"

    async def chat_stream(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self._call_count += 1
        if self._call_count >= self._max_calls:
            yield ChatStreamEvent(
                type="content", content="final answer"
            )
            yield ChatStreamEvent(type="done", tokens_used=5)
            return
        yield ChatStreamEvent(
            type="done",
            tokens_used=5,
            tool_name="echo",
            tool_params='{"text": "hello"}',
        )

    async def chat(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        return type("obj", (), {"content": "", "tokens_used": 0})()

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> Any:
        return type("obj", (), {"vectors": [], "model_used": "", "dimensions": 0})()

    async def check_health(self) -> Any:
        return type("obj", (), {"ok": True, "latency_ms": 0, "error": None})()


class TestToolIntegration:

    @pytest.mark.asyncio
    async def test_tool_call_via_done_event(self) -> None:
        first = [
            ChatStreamEvent(
                type="content", content="Let me check the time"
            ),
            ChatStreamEvent(
                type="done",
                tokens_used=10,
                tool_name="get_current_time",
                tool_params="{}",
            ),
        ]
        second = [
            ChatStreamEvent(
                type="content", content="The time is now."
            ),
            ChatStreamEvent(type="done", tokens_used=5),
        ]
        provider = ToolCallProvider(first, second)
        store = BeliefStore()
        reader = Reader(store)
        tool_registry = MockToolRegistry()
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
            tool_registry=tool_registry,
        )
        tokens = []
        async for token in agent.chat_stream(
            message="what time is it", conversation_id="conv_1"
        ):
            tokens.append(token)
        assert "".join(tokens) == "Let me check the timeThe time is now."
        beliefs = await store.get("conv_1")
        sources = [b.source for b in beliefs]
        assert "user" in sources
        assert "tool" in sources
        assert "assistant" in sources

    @pytest.mark.asyncio
    async def test_tool_result_in_belief_store(self) -> None:
        first = [
            ChatStreamEvent(
                type="done",
                tokens_used=5,
                tool_name="echo",
                tool_params='{"text": "hello world"}',
            ),
        ]
        second = [
            ChatStreamEvent(
                type="content", content="Echo done"
            ),
            ChatStreamEvent(type="done", tokens_used=3),
        ]
        provider = ToolCallProvider(first, second)
        store = BeliefStore()
        reader = Reader(store)
        tool_registry = MockToolRegistry()
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
            tool_registry=tool_registry,
        )
        async for _ in agent.chat_stream(
            message="echo hello", conversation_id="conv_1"
        ):
            pass
        beliefs = await store.get("conv_1")
        tool_beliefs = [b for b in beliefs if b.source == "tool"]
        assert len(tool_beliefs) == 1
        assert "echo: hello world" in tool_beliefs[0].content

    @pytest.mark.asyncio
    async def test_max_tool_calls_limit(self) -> None:
        provider = AlwaysToolProvider(max_calls=4)
        store = BeliefStore()
        reader = Reader(store)
        tool_registry = MockToolRegistry()
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
            tool_registry=tool_registry,
        )
        tokens = []
        async for token in agent.chat_stream(
            message="do tool", conversation_id="conv_1"
        ):
            tokens.append(token)
        combined = "".join(tokens)
        assert "final answer" in combined

    @pytest.mark.asyncio
    async def test_tool_execution_error_handling(self) -> None:
        class ErrorToolRegistry(IToolRegistry):

            async def execute(
                self, tool_name: str, arguments: dict[str, Any]
            ) -> str:
                msg = f"simulated error for {tool_name}"
                raise RuntimeError(msg)

            def list_tools(self) -> list[ToolSpec]:
                return []

            def get_tool(
                self, tool_name: str
            ) -> ToolSpec | None:
                return None

        first = [
            ChatStreamEvent(
                type="done",
                tokens_used=3,
                tool_name="broken_tool",
                tool_params="{}",
            ),
        ]
        second = [
            ChatStreamEvent(
                type="content",
                content="Tool failed but continuing",
            ),
            ChatStreamEvent(type="done", tokens_used=5),
        ]
        provider = ToolCallProvider(first, second)
        store = BeliefStore()
        reader = Reader(store)
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
            tool_registry=ErrorToolRegistry(),
        )
        tokens = []
        async for token in agent.chat_stream(
            message="run tool", conversation_id="conv_1"
        ):
            tokens.append(token)
        assert "Tool failed but continuing" in "".join(tokens)

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from src.core.agent import Agent
from src.core.belief_store import BeliefStore
from src.core.reader import Reader
from src.models.interfaces import ChatStreamEvent, IModelProvider


class MockStreamProvider(IModelProvider):

    def __init__(self, responses: list[list[ChatStreamEvent]]) -> None:
        self._responses = responses
        self._call_count = 0
        self._histories: list[list[dict[str, Any]]] = []

    @property
    def name(self) -> str:
        return "mock"

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


class TestAgent:

    def _make_agent(
        self, provider: IModelProvider
    ) -> Agent:
        store = BeliefStore()
        reader = Reader(store)
        return Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
        )

    @pytest.mark.asyncio
    async def test_chat_stream_basic(self) -> None:
        provider = MockStreamProvider(
            [
                [
                    ChatStreamEvent(
                        type="content", content="Hello! "
                    ),
                    ChatStreamEvent(
                        type="content", content="How can I help?"
                    ),
                    ChatStreamEvent(type="done", tokens_used=10),
                ]
            ]
        )
        agent = self._make_agent(provider)
        tokens = []
        async for token in agent.chat_stream(
            message="hi", conversation_id="conv_1"
        ):
            tokens.append(token)
        assert "".join(tokens) == "Hello! How can I help?"

    @pytest.mark.asyncio
    async def test_chat_stream_auto_conversation_id(self) -> None:
        provider = MockStreamProvider(
            [
                [
                    ChatStreamEvent(
                        type="content", content="reply"
                    ),
                    ChatStreamEvent(type="done", tokens_used=5),
                ]
            ]
        )
        agent = self._make_agent(provider)
        tokens = []
        async for token in agent.chat_stream(message="hello"):
            tokens.append(token)
        assert "".join(tokens) == "reply"

    @pytest.mark.asyncio
    async def test_chat_stream_context_contains_user_message(
        self,
    ) -> None:
        provider = MockStreamProvider(
            [
                [
                    ChatStreamEvent(
                        type="content", content="ok"
                    ),
                    ChatStreamEvent(type="done", tokens_used=3),
                ]
            ]
        )
        store = BeliefStore()
        reader = Reader(store)
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
        )
        async for _ in agent.chat_stream(
            message="user msg", conversation_id="conv_1"
        ):
            pass
        beliefs = await store.get("conv_1")
        assert len(beliefs) == 2
        assert beliefs[0].source == "user"
        assert beliefs[0].content == "user msg"
        assert beliefs[1].source == "assistant"
        assert beliefs[1].content == "ok"

    @pytest.mark.asyncio
    async def test_multiple_conversations_isolated(self) -> None:
        provider = MockStreamProvider(
            [
                [
                    ChatStreamEvent(
                        type="content", content="reply_a"
                    ),
                    ChatStreamEvent(type="done", tokens_used=3),
                ],
                [
                    ChatStreamEvent(
                        type="content", content="reply_b"
                    ),
                    ChatStreamEvent(type="done", tokens_used=3),
                ],
            ]
        )
        store = BeliefStore()
        reader = Reader(store)
        agent = Agent(
            model_provider=provider,
            belief_store=store,
            reader=reader,
        )
        async for _ in agent.chat_stream(
            message="msg1", conversation_id="conv_a"
        ):
            pass
        async for _ in agent.chat_stream(
            message="msg2", conversation_id="conv_b"
        ):
            pass
        assert len(await store.get("conv_a")) == 2
        assert len(await store.get("conv_b")) == 2
        assert (await store.get("conv_a"))[0].content == "msg1"
        assert (await store.get("conv_b"))[0].content == "msg2"

    @pytest.mark.asyncio
    async def test_chat_stream_multiple_rounds(self) -> None:
        provider = MockStreamProvider(
            [
                [
                    ChatStreamEvent(
                        type="content", content="round1"
                    ),
                    ChatStreamEvent(type="done", tokens_used=5),
                ],
                [
                    ChatStreamEvent(
                        type="content", content="round2"
                    ),
                    ChatStreamEvent(type="done", tokens_used=5),
                ],
            ]
        )
        agent = self._make_agent(provider)
        tokens1 = []
        async for token in agent.chat_stream(
            message="first", conversation_id="conv_1"
        ):
            tokens1.append(token)
        tokens2 = []
        async for token in agent.chat_stream(
            message="second", conversation_id="conv_1"
        ):
            tokens2.append(token)
        assert "".join(tokens1) == "round1"
        assert "".join(tokens2) == "round2"

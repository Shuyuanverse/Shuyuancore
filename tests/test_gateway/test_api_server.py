from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.agent import Agent
from src.core.belief_store import BeliefStore
from src.core.reader import Reader
from src.gateway.api_server import create_app, set_agent, set_belief_store
from src.memory.belief_store import PersistentBeliefStore
from src.models.interfaces import IModelProvider


@pytest.fixture(autouse=True)
def _reset_globals() -> None:
    import src.gateway.api_server as server_mod

    server_mod._agent_instance = None
    server_mod._belief_store_instance = None


class _MockModelProvider(IModelProvider):
    @property
    def name(self) -> str:
        return "mock"

    async def chat(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        from src.models.interfaces import ChatResult

        return ChatResult(content="mock response", tokens_used=10)

    async def chat_stream(
        self,
        history: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[Any]:
        from src.models.interfaces import ChatStreamEvent

        for ch in "Hello from mock":
            yield ChatStreamEvent(type="content", content=ch)
        yield ChatStreamEvent(type="done")

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> Any:
        from src.models.interfaces import EmbeddingResult

        return EmbeddingResult(vectors=[[0.0] * 1536 for _ in texts], dimensions=1536)

    async def check_health(self) -> Any:
        from src.models.interfaces import HealthStatus

        return HealthStatus(ok=True, latency_ms=10)


@pytest.fixture
def test_db_path(tmp_path: Any) -> str:
    return str(tmp_path / "test_state.db")


@pytest.fixture
def persistent_store(test_db_path: str) -> PersistentBeliefStore:
    return PersistentBeliefStore(db_path=test_db_path)


@pytest.fixture
def memory_store() -> BeliefStore:
    return BeliefStore()


@pytest.fixture
def mock_agent(memory_store: BeliefStore) -> Agent:
    reader = Reader(memory_store)
    return Agent(
        model_provider=_MockModelProvider(),
        belief_store=memory_store,
        reader=reader,
    )


@pytest.fixture
def mock_agent_persistent(persistent_store: PersistentBeliefStore) -> Agent:
    reader = Reader(persistent_store)
    return Agent(
        model_provider=_MockModelProvider(),
        belief_store=persistent_store,
        reader=reader,
    )


class TestHealthEndpoint:
    async def test_health_returns_healthy(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"


class TestChatEndpoint:
    async def test_chat_non_streaming_returns_response(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "Hello", "conversation_id": "test-conv-1"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Hello from mock"
        assert data["conversation_id"] == "test-conv-1"
        assert "message_id" in data
        assert data["approval_required"] is False

    async def test_chat_auto_generates_conversation_id(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "Hello"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"]
        assert "-" in data["conversation_id"]

    async def test_chat_empty_message_rejected(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": ""},
            )
        assert resp.status_code == 422

    async def test_chat_agent_not_available(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "Hello"},
            )
        assert resp.status_code == 503


class TestConversationsEndpoint:
    async def test_list_empty_conversations(self, persistent_store: PersistentBeliefStore) -> None:
        set_belief_store(persistent_store)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False

    async def test_list_conversations_with_data(
        self, mock_agent_persistent: Agent, persistent_store: PersistentBeliefStore
    ) -> None:
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        conv_id_1 = str(uuid.uuid4())
        conv_id_2 = str(uuid.uuid4())

        await mock_agent_persistent.chat_stream("msg a1", conv_id_1).__anext__()
        async for _ in mock_agent_persistent.chat_stream("msg a1", conv_id_1):
            pass
        await mock_agent_persistent.chat_stream("msg a2", conv_id_1).__anext__()
        async for _ in mock_agent_persistent.chat_stream("msg a2", conv_id_1):
            pass
        await mock_agent_persistent.chat_stream("msg b1", conv_id_2).__anext__()
        async for _ in mock_agent_persistent.chat_stream("msg b1", conv_id_2):
            pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    async def test_conversations_pagination(
        self, mock_agent_persistent: Agent, persistent_store: PersistentBeliefStore
    ) -> None:
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        for i in range(5):
            conv_id = f"conv-page-{i}"
            await mock_agent_persistent.chat_stream(f"msg {i}", conv_id).__anext__()
            async for _ in mock_agent_persistent.chat_stream(f"msg {i}", conv_id):
                pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/conversations", params={"limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        next_cursor = data["next_cursor"]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp2 = await client.get(
                "/api/v1/conversations", params={"limit": 2, "cursor": next_cursor}
            )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) > 0


class TestMessagesEndpoint:
    async def test_list_messages_empty(self, persistent_store: PersistentBeliefStore) -> None:
        set_belief_store(persistent_store)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/conversations/nonexistent/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []

    async def test_list_messages_with_data(
        self, mock_agent_persistent: Agent, persistent_store: PersistentBeliefStore
    ) -> None:
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        conv_id = str(uuid.uuid4())
        await mock_agent_persistent.chat_stream("question 1", conv_id).__anext__()
        async for _ in mock_agent_persistent.chat_stream("question 1", conv_id):
            pass
        await mock_agent_persistent.chat_stream("question 2", conv_id).__anext__()
        async for _ in mock_agent_persistent.chat_stream("question 2", conv_id):
            pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/conversations/{conv_id}/messages")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 2

        roles = [item["role"] for item in data["items"]]
        assert "user" in roles
        assert "assistant" in roles

    async def test_messages_pagination(
        self, mock_agent_persistent: Agent, persistent_store: PersistentBeliefStore
    ) -> None:
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        conv_id = str(uuid.uuid4())
        for i in range(5):
            await mock_agent_persistent.chat_stream(f"msg {i}", conv_id).__anext__()
            async for _ in mock_agent_persistent.chat_stream(f"msg {i}", conv_id):
                pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/conversations/{conv_id}/messages", params={"limit": 3}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["has_more"] is True

        next_cursor = data["next_cursor"]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp2 = await client.get(
                f"/api/v1/conversations/{conv_id}/messages",
                params={"limit": 10, "cursor": next_cursor},
            )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) > 0


class TestRequestIdMiddleware:
    async def test_request_id_header_present(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers


class TestCorsMiddleware:
    async def test_cors_headers_present(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.options(
                "/health",
                headers={
                    "Origin": "http://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


class TestChatStreamEndpoint:
    async def test_sse_stream_returns_events(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "Hello", "conversation_id": "test-conv-sse"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")

                raw = ""
                async for chunk in response.aiter_text():
                    raw += chunk

        lines = [line for line in raw.split("\n") if line]
        events = []
        for i in range(0, len(lines), 2):
            if (
                i + 1 < len(lines)
                and lines[i].startswith("event:")
                and lines[i + 1].startswith("data:")
            ):
                events.append(
                    {
                        "event": lines[i][7:],
                        "data": lines[i + 1][6:],
                    }
                )

        assert len(events) > 0
        event_types = [e["event"] for e in events]
        assert "message" in event_types
        assert "done" in event_types

    async def test_sse_stream_content_assembles(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "Hi"},
            ) as response:
                raw = ""
                async for chunk in response.aiter_text():
                    raw += chunk

        content_parts = []
        for line in raw.split("\n"):
            if line.startswith("data:"):
                try:
                    data = json.loads(line[6:])
                    if "content" in data:
                        content_parts.append(data["content"])
                except json.JSONDecodeError:
                    pass

        assembled = "".join(content_parts)
        assert assembled == "Hello from mock"

    async def test_sse_done_event_has_conversation_id(self, mock_agent: Agent) -> None:
        set_agent(mock_agent)
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "Hi", "conversation_id": "conv-done-test"},
            ) as response:
                raw = ""
                async for chunk in response.aiter_text():
                    raw += chunk

        assert "conv-done-test" in raw

    async def test_sse_rejects_empty_message(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat/stream",
                json={"message": ""},
            )
        assert resp.status_code == 422


class TestUserIsolation:
    async def test_conversations_isolated_by_user_header(
        self, mock_agent_persistent, persistent_store
    ) -> None:
        from src.gateway.api_server import set_agent, set_belief_store
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        conv_a = str(uuid.uuid4())
        conv_b = str(uuid.uuid4())

        await mock_agent_persistent.chat_stream("msg a", conv_a).__anext__()
        async for _ in mock_agent_persistent.chat_stream("msg a", conv_a):
            pass
        await mock_agent_persistent.chat_stream("msg b", conv_b).__anext__()
        async for _ in mock_agent_persistent.chat_stream("msg b", conv_b):
            pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/conversations",
                headers={"X-User-ID": "user-a"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 0

    async def test_conversations_with_matching_user_id(
        self, mock_agent_persistent, persistent_store
    ) -> None:
        from src.gateway.api_server import set_agent, set_belief_store
        set_agent(mock_agent_persistent)
        set_belief_store(persistent_store)

        conv_id = str(uuid.uuid4())
        await mock_agent_persistent.chat_stream("hello", conv_id).__anext__()
        async for _ in mock_agent_persistent.chat_stream("hello", conv_id):
            pass

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/conversations",
                headers={"X-User-ID": "anonymous"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1

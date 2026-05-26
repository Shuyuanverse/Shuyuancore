from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.core.agent import Agent
from src.core.belief_store import BeliefStore
from src.core.reader import Reader
from src.gateway.cli_repl import (
    _CommandCompleter,
    _handle_command,
    _handle_user_message,
    set_agent,
)
from src.models.interfaces import IModelProvider
from src.security.approval import get_approval_manager


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

        yield ChatStreamEvent(type="content", content="Hello")
        yield ChatStreamEvent(type="content", content=" from")
        yield ChatStreamEvent(type="content", content=" mock")
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
def mock_agent() -> Agent:
    store = BeliefStore()
    reader = Reader(store)
    return Agent(
        model_provider=_MockModelProvider(),
        belief_store=store,
        reader=reader,
    )


@pytest.fixture(autouse=True)
def _reset_approval_manager() -> None:
    mgr = get_approval_manager()
    mgr._requests.clear()
    mgr._counter = 0


@pytest.fixture(autouse=True)
def _reset_agent_global() -> None:
    import src.gateway.cli_repl as cli_mod

    cli_mod._agent = None
    cli_mod._current_mode = "balanced"


class TestCommandCompleter:
    def test_completes_commands(self) -> None:
        from prompt_toolkit.document import Document

        completer = _CommandCompleter()
        doc = Document("/mo", 3)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "/mode" in texts

    def test_completes_mode_subcommand(self) -> None:
        from prompt_toolkit.document import Document

        completer = _CommandCompleter()
        doc = Document("/mode qui", 9)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "quick" in texts

    def test_does_not_complete_non_command(self) -> None:
        from prompt_toolkit.document import Document

        completer = _CommandCompleter()
        doc = Document("hello", 5)
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 0


class TestHandleCommand:
    async def test_exit_command_returns_true(self) -> None:
        from unittest.mock import MagicMock

        session = MagicMock()
        result = await _handle_command("/exit", session)
        assert result is True

    async def test_quit_command_returns_true(self) -> None:
        from unittest.mock import MagicMock

        session = MagicMock()
        result = await _handle_command("/quit", session)
        assert result is True

    async def test_mode_switch(self) -> None:
        from unittest.mock import MagicMock

        import src.gateway.cli_repl as cli_mod

        session = MagicMock()
        await _handle_command("/mode quick", session)
        assert cli_mod._current_mode == "quick"

        await _handle_command("/mode deep", session)
        assert cli_mod._current_mode == "deep"

        await _handle_command("/mode balanced", session)
        assert cli_mod._current_mode == "balanced"

    async def test_mode_invalid(self) -> None:
        from unittest.mock import MagicMock

        import src.gateway.cli_repl as cli_mod

        session = MagicMock()
        cli_mod._current_mode = "balanced"
        await _handle_command("/mode invalid", session)
        assert cli_mod._current_mode == "balanced"

    async def test_approve_command(self) -> None:
        from unittest.mock import MagicMock

        mgr = get_approval_manager()
        req = await mgr.request(
            tool_name="test", params={}, user_id="test-user"
        )
        aid = req.approval_id

        session = MagicMock()
        result = await _handle_command(f"/approve {aid}", session)
        assert result is False

        resolved = mgr.get_request(aid)
        assert resolved is not None
        assert resolved.status == "approved"

    async def test_deny_command(self) -> None:
        from unittest.mock import MagicMock

        mgr = get_approval_manager()
        req = await mgr.request(
            tool_name="test", params={}, user_id="test-user"
        )
        aid = req.approval_id

        session = MagicMock()
        result = await _handle_command(f"/deny {aid}", session)
        assert result is False

        resolved = mgr.get_request(aid)
        assert resolved is not None
        assert resolved.status == "denied"

    async def test_approve_nonexistent(self) -> None:
        from unittest.mock import MagicMock

        session = MagicMock()
        result = await _handle_command("/approve fake-id", session)
        assert result is False

    async def test_unknown_command(self) -> None:
        from unittest.mock import MagicMock

        session = MagicMock()
        result = await _handle_command("/foobar", session)
        assert result is False


class TestHandleUserMessage:
    async def test_handle_user_message_with_mock_agent(
        self, mock_agent: Agent, capsys: Any
    ) -> None:
        set_agent(mock_agent)
        await _handle_user_message("Hello", "test-conv")
        captured = capsys.readouterr()
        assert "Hello from mock" in captured.out

    async def test_handle_user_message_agent_unavailable(
        self, capsys: Any
    ) -> None:
        import src.gateway.cli_repl as cli_mod

        cli_mod._agent = None
        await _handle_user_message("Hello", "test-conv")

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import (
    ITool,
    IToolRegistry,
    ToolParameter,
    ToolResult,
    ToolSpec,
)
from src.tools.registry import ToolRegistry


class TestToolSpecCreation:

    def test_tool_parameter_defaults(self) -> None:
        param = ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch",
        )
        assert param.name == "url"
        assert param.type == "string"
        assert param.description == "The URL to fetch"
        assert param.required is False
        assert param.default is None

    def test_tool_parameter_required_with_default(self) -> None:
        param = ToolParameter(
            name="timeout",
            type="integer",
            description="Request timeout",
            required=True,
            default=30,
        )
        assert param.name == "timeout"
        assert param.required is True
        assert param.default == 30

    def test_tool_spec_defaults(self) -> None:
        spec = ToolSpec(
            name="web_fetch",
            description="Fetch a web page",
            category="web",
        )
        assert spec.name == "web_fetch"
        assert spec.description == "Fetch a web page"
        assert spec.category == "web"
        assert spec.parameters == []
        assert spec.dangerous is False
        assert spec.require_sandbox is False
        assert spec.require_approval is False

    def test_tool_spec_with_parameters(self) -> None:
        params = [
            ToolParameter(name="url", type="string", description="Target URL", required=True),
            ToolParameter(name="timeout", type="integer", description="Timeout in seconds", default=30),
        ]
        spec = ToolSpec(
            name="web_fetch",
            description="Fetch a web page",
            category="web",
            parameters=params,
            dangerous=True,
            require_sandbox=True,
        )
        assert len(spec.parameters) == 2
        assert spec.dangerous is True
        assert spec.require_sandbox is True

    def test_tool_result_creation(self) -> None:
        result = ToolResult(
            success=True,
            data={"title": "Example", "content": "Hello"},
            duration_ms=12.5,
        )
        assert result.success is True
        assert result.data == {"title": "Example", "content": "Hello"}
        assert result.duration_ms == 12.5
        assert result.error == ""
        assert result.approval_id == ""

    def test_tool_result_error(self) -> None:
        result = ToolResult(
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"


class TestToolResultToDict:

    def test_to_dict_full(self) -> None:
        result = ToolResult(
            success=True,
            data="result_data",
            error="",
            duration_ms=42.0,
            approval_id="apr_123",
        )
        d = result.to_dict()
        assert d == {
            "success": True,
            "data": "result_data",
            "error": "",
            "duration_ms": 42.0,
            "approval_id": "apr_123",
        }

    def test_to_dict_empty(self) -> None:
        result = ToolResult(success=False)
        d = result.to_dict()
        assert d["success"] is False
        assert d["data"] is None
        assert d["error"] == ""
        assert d["duration_ms"] == 0.0
        assert d["approval_id"] == ""


class TestApproval:

    @pytest.fixture(autouse=True)
    async def _reset_approval_manager(self) -> None:
        from src.security.approval import _managers

        for mgr in list(_managers.values()):
            await mgr.cleanup(max_age=0)
        _managers.clear()

    @pytest.mark.asyncio
    async def test_approval_request_and_resolve(self) -> None:
        mgr = await get_approval_manager()
        req = await mgr.request(
            tool_name="delete_file",
            params={"path": "/tmp/test.txt"},
            user_id="user_1",
            timeout=300,
        )
        assert req.status == "pending"
        assert req.approved is None
        assert req.tool_name == "delete_file"
        assert req.user_id == "user_1"

        resolved = await mgr.resolve(
            approval_id=req.approval_id,
            approved=True,
            reason="User confirmed",
            resolved_by="admin",
        )
        assert resolved.status == "approved"
        assert resolved.approved is True
        assert resolved.reason == "User confirmed"
        assert resolved.resolved_by == "admin"
        assert resolved.resolved_at > 0

        waited = await mgr.wait(req.approval_id, timeout=5)
        assert waited is True

    @pytest.mark.asyncio
    async def test_approval_wait_timeout(self) -> None:
        mgr = await get_approval_manager()
        req = await mgr.request(
            tool_name="delete_file",
            params={"path": "/tmp/test.txt"},
            user_id="user_1",
            timeout=1,
        )
        result = await mgr.wait(req.approval_id, timeout=0.1)
        assert result is False

        updated = await mgr.aget_request(req.approval_id)
        assert updated is not None
        assert updated.status == "timeout"
        assert updated.approved is False
        assert updated.reason != ""

    @pytest.mark.asyncio
    async def test_approval_list_pending(self) -> None:
        mgr = await get_approval_manager()
        req1 = await mgr.request(
            tool_name="tool_a", params={}, user_id="user_1", timeout=300,
        )
        req2 = await mgr.request(
            tool_name="tool_b", params={}, user_id="user_2", timeout=300,
        )
        pending_1 = await mgr.list_pending_by_user("user_1")
        assert len(pending_1) == 1
        assert req1.approval_id == pending_1[0].approval_id
        pending_2 = await mgr.list_pending_by_user("user_2")
        assert len(pending_2) == 1
        assert req2.approval_id == pending_2[0].approval_id

        await mgr.resolve(req1.approval_id, approved=True)
        pending_1 = await mgr.list_pending_by_user("user_1")
        assert len(pending_1) == 0
        pending_2 = await mgr.list_pending_by_user("user_2")
        assert len(pending_2) == 1
        assert pending_2[0].approval_id == req2.approval_id


class TestAuditLogger:

    @pytest.fixture(autouse=True)
    def _reset_audit_logger(self) -> None:
        get_audit_logger()._cache.clear()

    def test_audit_logger_log(self) -> None:
        audit = get_audit_logger()
        audit.log(
            user_id="user_1",
            action="tool_execute",
            resource="tool:web_fetch",
            params={"url": "https://example.com"},
            result="success",
            duration_ms=10.5,
        )
        entries = audit.get_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["user_id"] == "user_1"
        assert entry["action"] == "tool_execute"
        assert entry["resource"] == "tool:web_fetch"
        assert entry["params"] == {"url": "https://example.com"}
        assert entry["result"] == "success"
        assert entry["duration_ms"] == 10.5
        assert entry["approved"] is None

    def test_audit_logger_sanitize(self) -> None:
        audit = get_audit_logger()
        audit.log(
            user_id="user_1",
            action="tool_execute",
            resource="tool:api_call",
            params={"url": "https://api.example.com", "api_key": "sk-1234567890abcdef"},
            result="success",
        )
        entries = audit.get_entries()
        assert len(entries) == 1
        assert entries[0]["params"]["api_key"] == "***REDACTED***"
        assert entries[0]["params"]["url"] == "https://api.example.com"

    def test_audit_logger_get_entries_filter(self) -> None:
        audit = get_audit_logger()
        audit.log(
            user_id="alice",
            action="tool_execute",
            resource="tool:web_fetch",
            params={},
            result="success",
        )
        audit.log(
            user_id="bob",
            action="tool_execute",
            resource="tool:delete_file",
            params={},
            result="success",
        )
        audit.log(
            user_id="alice",
            action="tool_execute",
            resource="tool:send_email",
            params={},
            result="error",
        )

        alice_entries = audit.get_entries(user_id="alice")
        assert len(alice_entries) == 2

        bob_entries = audit.get_entries(user_id="bob")
        assert len(bob_entries) == 1

        error_entries = audit.get_entries(action="tool_execute")
        assert len(error_entries) == 3

    def test_audit_logger_max_entries(self) -> None:
        audit = get_audit_logger()
        original_max = audit._max_entries
        audit._max_entries = 10
        for i in range(15):
            audit.log(
                user_id=f"user_{i}",
                action="test",
                resource="test",
                params={"n": i},
            )
        entries = audit.get_entries()
        assert len(entries) == 9
        assert entries[0]["params"]["n"] == 6
        audit._max_entries = original_max


class TestSandbox:

    @pytest.fixture(autouse=True)
    def _patch_subprocess(self) -> None:
        self._patcher = patch(
            "src.security.sandbox.asyncio.create_subprocess_exec",
        )
        self._mock_create_subprocess = self._patcher.start()
        yield
        self._patcher.stop()

    def _make_mock_process(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(
            return_value=(stdout.encode(), stderr.encode())
        )
        return proc

    @pytest.mark.asyncio
    async def test_sandbox_execute_local_success(self) -> None:
        from src.security.sandbox import SandboxExecutor

        mock_proc = self._make_mock_process(
            returncode=0,
            stdout="hello world\n",
        )
        self._mock_create_subprocess.return_value = mock_proc

        executor = SandboxExecutor(sandbox_mode="local")
        executor._docker_available = False

        result = await executor.execute(
            command=["echo", "hello world"],
            timeout=10,
        )
        assert result.success is True
        assert result.stdout == "hello world\n"
        assert result.stderr == ""
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_sandbox_execute_local_timeout(self) -> None:
        from src.security.sandbox import SandboxExecutor

        original_wait_for = asyncio.wait_for

        async def _timeout_wait_for(coro, timeout, **kwargs):  # type: ignore[no-untyped-def]
            raise asyncio.TimeoutError()

        with patch("src.security.sandbox.asyncio.wait_for", _timeout_wait_for):
            mock_proc = self._make_mock_process()
            self._mock_create_subprocess.return_value = mock_proc

            executor = SandboxExecutor(sandbox_mode="local")
            executor._docker_available = False

            result = await executor.execute(
                command=["sleep", "100"],
                timeout=0.1,
            )
            assert result.success is False
            assert "timeout" in result.error.lower()
            assert result.exit_code == -1


class TestRegistry:

    @pytest.fixture(autouse=True)
    async def _reset_registry(self) -> None:
        self.registry = ToolRegistry()
        mgr = await get_approval_manager()
        mgr._events.clear()
        get_audit_logger()._cache.clear()

    @pytest.mark.asyncio
    async def test_registry_register_and_list(self) -> None:
        mock_tool = MagicMock(spec=ITool)
        mock_tool.get_spec.return_value = ToolSpec(
            name="echo",
            description="Echo input back",
            category="utility",
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text to echo",
                    required=True,
                ),
            ],
        )

        self.registry.register(mock_tool)
        tools = self.registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"
        assert tools[0].category == "utility"
        assert len(tools[0].parameters) == 1

        filtered = self.registry.list_tools(category="utility")
        assert len(filtered) == 1

        empty = self.registry.list_tools(category="web")
        assert len(empty) == 0

    @pytest.mark.asyncio
    async def test_registry_execute_tool_not_found(self) -> None:
        result = await self.registry.execute_tool(
            name="nonexistent_tool",
            params={},
        )
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_registry_execute_tool_dangerous_denied(self) -> None:
        mock_tool = MagicMock(spec=ITool)
        mock_tool.get_spec.return_value = ToolSpec(
            name="delete_file",
            description="Delete a file",
            category="file",
            dangerous=True,
        )
        mock_tool.validate = AsyncMock(return_value=[])

        self.registry.register(mock_tool)

        mgr = await get_approval_manager()
        with patch.object(
            mgr,
            "wait",
            AsyncMock(return_value=False),
        ):
            result = await self.registry.execute_tool(
                name="delete_file",
                params={"path": "/tmp/test.txt"},
                user_id="user_1",
            )
            assert result.success is False
            assert "denied" in result.error
            assert result.approval_id != ""

        mock_tool.execute.assert_not_called()
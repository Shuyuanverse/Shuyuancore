from __future__ import annotations

import asyncio

import pytest

from src.security.approval import (
    ApprovalManager,
    get_approval_manager,
)


class TestApprovalManagerBasics:
    @pytest.mark.asyncio
    async def test_request_creates_persistent_record(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="terminal",
            params={"command": "ls -la"},
            user_id="user_a",
            timeout=300,
        )

        assert req.approval_id.startswith("user_a_")
        assert req.tool_name == "terminal"
        assert req.status == "pending"
        assert req.user_id == "user_a"

        fetched = await mgr.aget_request(req.approval_id)
        assert fetched is not None
        assert fetched.approval_id == req.approval_id
        assert fetched.tool_name == "terminal"
        assert fetched.status == "pending"

        await mgr.close()

    @pytest.mark.asyncio
    async def test_resolve_updates_persistent_record(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="file_write",
            params={"path": "/tmp/test.txt"},
            user_id="user_a",
        )

        resolved = await mgr.resolve(
            approval_id=req.approval_id,
            approved=True,
            reason="Looks safe",
        )

        assert resolved.approved is True
        assert resolved.status == "approved"
        assert resolved.reason == "Looks safe"

        fetched = await mgr.aget_request(req.approval_id)
        assert fetched is not None
        assert fetched.status == "approved"
        assert fetched.approved is True

        await mgr.close()

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_raises(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        with pytest.raises(ValueError, match="not found"):
            await mgr.resolve("nonexistent_id", True)
        await mgr.close()

    @pytest.mark.asyncio
    async def test_deny_updates_record(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="web_request",
            params={"url": "http://example.com"},
            user_id="user_a",
        )

        resolved = await mgr.resolve(
            approval_id=req.approval_id,
            approved=False,
            reason="Blocked",
        )

        assert resolved.approved is False
        assert resolved.status == "denied"

        await mgr.close()


class TestApprovalUserIsolation:
    @pytest.mark.asyncio
    async def test_two_users_isolated(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req_a = await mgr.request(
            tool_name="terminal",
            params={"command": "ls"},
            user_id="user_a",
        )
        req_b = await mgr.request(
            tool_name="terminal",
            params={"command": "rm -rf /"},
            user_id="user_b",
        )

        pending_a = await mgr.list_pending_by_user("user_a")
        pending_b = await mgr.list_pending_by_user("user_b")

        assert len(pending_a) == 1
        assert len(pending_b) == 1
        assert pending_a[0].approval_id == req_a.approval_id
        assert pending_b[0].approval_id == req_b.approval_id
        assert pending_a[0].user_id == "user_a"
        assert pending_b[0].user_id == "user_b"

        await mgr.resolve(req_a.approval_id, True)
        await mgr.resolve(req_b.approval_id, False)

        pending_a2 = await mgr.list_pending_by_user("user_a")
        pending_b2 = await mgr.list_pending_by_user("user_b")
        assert len(pending_a2) == 0
        assert len(pending_b2) == 0

        await mgr.close()

    @pytest.mark.asyncio
    async def test_appoval_id_format_includes_user_id(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="test",
            params={},
            user_id="specific_user",
        )

        assert "specific_user_" == req.approval_id[:14]
        assert req.approval_id.startswith("specific_user_")
        await mgr.close()


class TestApprovalWaitAndTimeout:
    @pytest.mark.asyncio
    async def test_wait_returns_when_resolved(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="test",
            params={},
            user_id="user_a",
            timeout=30,
        )

        async def resolve_after_delay() -> None:
            await asyncio.sleep(0.1)
            await mgr.resolve(req.approval_id, True)

        task = asyncio.create_task(resolve_after_delay())

        result = await mgr.wait(req.approval_id, timeout=5)
        assert result is True

        await task
        await mgr.close()

    @pytest.mark.asyncio
    async def test_wait_times_out(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"
        mgr = ApprovalManager(db_path=db_path)
        await mgr.initialize()

        req = await mgr.request(
            tool_name="test",
            params={},
            user_id="user_a",
            timeout=1,
        )

        result = await mgr.wait(req.approval_id, timeout=1)
        assert result is False

        fetched = await mgr.aget_request(req.approval_id)
        assert fetched is not None
        assert fetched.status == "timeout"

        await mgr.close()


class TestApprovalFactory:
    @pytest.mark.asyncio
    async def test_get_approval_manager_caches(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"

        mgr1 = await get_approval_manager(db_path)
        mgr2 = await get_approval_manager(db_path)

        assert mgr1 is mgr2

        await mgr1.close()
        await mgr2.close()


class TestApprovalPersistenceAcrossInstances:
    @pytest.mark.asyncio
    async def test_request_survives_new_instance(self, tmp_path: str) -> None:
        db_path = f"{tmp_path}/test_approvals.db"

        mgr1 = ApprovalManager(db_path=db_path)
        await mgr1.initialize()
        req = await mgr1.request(
            tool_name="test",
            params={"x": 1},
            user_id="user_a",
        )
        await mgr1.close()

        mgr2 = ApprovalManager(db_path=db_path)
        await mgr2.initialize()
        fetched = await mgr2.aget_request(req.approval_id)
        assert fetched is not None
        assert fetched.approval_id == req.approval_id
        assert fetched.status == "pending"
        assert fetched.user_id == "user_a"
        await mgr2.close()

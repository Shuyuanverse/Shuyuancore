from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.gateway.api_server import create_app


@ pytest.fixture(autouse=True)
def _reset_globals() -> None:
    import src.gateway.api_server as server_mod

    server_mod._agent_instance = None
    server_mod._belief_store_instance = None


class TestApprovalEndpoints:
    async def test_create_approval(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/approvals",
                headers={"X-User-ID": "test-user-1"},
                json={
                    "tool_name": "terminal",
                    "command": "rm -rf /",
                    "user_id": "test-user-1",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "test-user-1" in data["approval_id"]

    async def test_approve_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/approvals",
                headers={"X-User-ID": "test-user-2"},
                json={
                    "tool_name": "terminal",
                    "command": "ls",
                    "user_id": "test-user-2",
                },
            )
        approval_id = create_resp.json()["approval_id"]

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                json={"approved": True, "reason": "safe command"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["approval_id"] == approval_id

    async def test_deny_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/approvals",
                headers={"X-User-ID": "test-user-3"},
                json={
                    "tool_name": "file_ops",
                    "command": "delete all",
                    "user_id": "test-user-3",
                },
            )
        approval_id = create_resp.json()["approval_id"]

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/approvals/{approval_id}/deny",
                json={"approved": False, "reason": "too dangerous"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"
        assert data["approval_id"] == approval_id

    async def test_approval_not_found_returns_404(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/approvals/nonexistent-id/approve",
                json={"approved": True, "reason": ""},
            )
        assert resp.status_code == 404

    async def test_wait_approval_resolved_after_approve(self) -> None:
        from src.security.approval import ApprovalManager

        mgr = ApprovalManager(db_path="data/state.db")
        await mgr.initialize()
        req = await mgr.request(
            tool_name="terminal",
            params={"command": "ls"},
            user_id="test-user-wait",
            timeout=30,
        )
        approval_id = req.approval_id

        async def _approve_later() -> None:
            await asyncio.sleep(0.5)
            await mgr.resolve(approval_id, approved=True, reason="ok")

        asyncio.create_task(_approve_later())

        approved = await mgr.wait(approval_id, timeout=5)
        assert approved is True
        await mgr.close()

    async def test_approval_id_unique_per_user(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        ids = set()
        for i in range(5):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/approvals",
                    headers={"X-User-ID": f"user-{i}"},
                    json={
                        "tool_name": "test",
                        "command": f"cmd-{i}",
                        "user_id": f"user-{i}",
                    },
                )
            approval_id = resp.json()["approval_id"]
            ids.add(approval_id)

        assert len(ids) == 5
        for aid in ids:
            assert len(aid) >= 10

    async def test_approval_without_user_id_uses_anonymous(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/approvals",
                json={
                    "tool_name": "test",
                    "command": "hello",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "anonymous" in data["approval_id"]

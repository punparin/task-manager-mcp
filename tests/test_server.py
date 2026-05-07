"""End-to-end checks on a couple of MCP tool wrappers in server.py.

The server module bails on import when OBSIDIAN_VAULT_PATH is unset, so
each test reloads it under a tmp-path env and swaps in a fresh TaskStore.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from task_manager_mcp.tasks import TaskStore


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    import task_manager_mcp.server as server_module
    importlib.reload(server_module)
    server_module.store = TaskStore(tmp_path)
    return server_module


def _run(coro):
    return asyncio.run(coro)


class TestUpdateTaskBlockedBy:
    def test_replace_blocked_by(self, srv):
        srv.store.create(title="A")
        srv.store.create(title="B")
        srv.store.create(title="C", blocked_by=["T-001"])
        result = _run(srv.update_task(task_id="T-003", blocked_by="T-002"))
        assert "Updated T-003" in result
        assert srv.store.get("T-003").blocked_by == ["T-002"]

    def test_clear_blocked_by_with_dash_sentinel(self, srv):
        srv.store.create(title="A")
        srv.store.create(title="B", blocked_by=["T-001"])
        result = _run(srv.update_task(task_id="T-002", blocked_by="-"))
        assert "Updated T-002" in result
        assert srv.store.get("T-002").blocked_by == []

    def test_rejects_missing_blocker(self, srv):
        srv.store.create(title="A")
        result = _run(srv.update_task(task_id="T-001", blocked_by="T-999"))
        assert result.startswith("ERROR:")
        assert "T-999 does not exist" in result

    def test_rejects_cycle(self, srv):
        srv.store.create(title="A")
        srv.store.create(title="B", blocked_by=["T-001"])
        # Trying to make T-001 blocked by T-002 would close the loop.
        result = _run(srv.update_task(task_id="T-001", blocked_by="T-002"))
        assert result.startswith("ERROR:")
        assert "cycle" in result.lower()


class TestUpdateTaskCompleted:
    def test_set_completed(self, srv):
        srv.store.create(title="A")
        result = _run(srv.update_task(task_id="T-001", completed="2026-04-20"))
        assert "Updated T-001" in result
        assert srv.store.get("T-001").completed == "2026-04-20"

    def test_clear_completed_with_dash_sentinel(self, srv):
        srv.store.create(title="A")
        # Seed a completed value first.
        srv.store.update("T-001", completed="2026-04-20")
        result = _run(srv.update_task(task_id="T-001", completed="-"))
        assert "Updated T-001" in result
        assert srv.store.get("T-001").completed is None

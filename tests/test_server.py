"""End-to-end checks on a couple of MCP tool wrappers in server.py.

The server module bails on import when OBSIDIAN_VAULT_PATH is unset, so
each test reloads it under a tmp-path env and swaps in a fresh TaskStore.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from task_manager_mcp.history import parse_history
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


class TestStatusHistory:
    def test_start_task_appends_history(self, srv):
        srv.store.create(title="A", status="Ready")
        _run(srv.start_task(task_id="T-001"))
        history = parse_history(srv.store.get("T-001").body)
        assert len(history) == 1
        assert history[0].old_status == "Ready"
        assert history[0].new_status == "In Progress"
        assert history[0].actor == "agent"

    def test_complete_task_appends_history(self, srv):
        srv.store.create(title="A", status="In Progress")
        _run(srv.complete_task(task_id="T-001"))
        history = parse_history(srv.store.get("T-001").body)
        assert history[-1].old_status == "In Progress"
        assert history[-1].new_status == "Done"

    def test_block_task_appends_history(self, srv):
        srv.store.create(title="A", status="Ready")
        _run(srv.block_task(task_id="T-001", reason="waiting on legal"))
        history = parse_history(srv.store.get("T-001").body)
        assert history[-1].new_status == "Blocked"

    def test_update_task_status_change_appends_history(self, srv):
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", status="Ready"))
        history = parse_history(srv.store.get("T-001").body)
        assert history[-1].old_status == "Backlog"
        assert history[-1].new_status == "Ready"

    def test_update_task_no_status_change_no_history_entry(self, srv):
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", priority="P1"))
        assert parse_history(srv.store.get("T-001").body) == []

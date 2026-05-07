"""End-to-end checks on a couple of MCP tool wrappers in server.py.

The server module bails on import when OBSIDIAN_VAULT_PATH is unset, so
each test reloads it under a tmp-path env and swaps in a fresh TaskStore.
"""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest

from task_manager_mcp.audit import read_audit
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


class TestStatusAudit:
    def test_start_task_records_transition(self, srv, tmp_path):
        srv.store.create(title="A", status="Ready")
        _run(srv.start_task(task_id="T-001"))
        entries = read_audit(tmp_path, task_id="T-001")
        assert len(entries) == 1
        assert entries[0]["old_status"] == "Ready"
        assert entries[0]["new_status"] == "In Progress"
        assert entries[0]["actor"] == "agent"
        assert srv.store.get("T-001").last_status_change

    def test_complete_task_records_transition(self, srv, tmp_path):
        srv.store.create(title="A", status="In Progress")
        _run(srv.complete_task(task_id="T-001"))
        entries = read_audit(tmp_path, task_id="T-001")
        assert entries[0]["new_status"] == "Done"

    def test_block_task_records_transition(self, srv, tmp_path):
        srv.store.create(title="A", status="Ready")
        _run(srv.block_task(task_id="T-001", reason="waiting on legal"))
        entries = read_audit(tmp_path, task_id="T-001")
        assert entries[0]["new_status"] == "Blocked"

    def test_update_task_status_change_records(self, srv, tmp_path):
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", status="Ready"))
        entries = read_audit(tmp_path, task_id="T-001")
        assert entries[0]["old_status"] == "Backlog"
        assert entries[0]["new_status"] == "Ready"
        assert srv.store.get("T-001").last_status_change

    def test_update_task_no_status_change_no_log_entry(self, srv, tmp_path):
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", priority="P1"))
        assert read_audit(tmp_path, task_id="T-001") == []

    def test_auto_promote_records_transition(self, srv, tmp_path):
        srv.store.create(title="Blocker", status="In Progress")
        srv.store.create(title="Dependent", status="Backlog", blocked_by=["T-001"])
        _run(srv.complete_task(task_id="T-001"))
        promoted_entries = read_audit(tmp_path, task_id="T-002")
        assert len(promoted_entries) == 1
        assert promoted_entries[0]["new_status"] == "Ready"


class TestListAudit:
    def test_filter_by_since(self, srv):
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", status="Ready"))
        out = _run(srv.list_audit(since="2020-01-01"))
        parsed = json.loads(out)
        assert any(e["task_id"] == "T-001" for e in parsed)

    def test_invalid_since_returns_error(self, srv):
        out = _run(srv.list_audit(since="last week"))
        assert out.startswith("ERROR:")

    def test_empty_log_message(self, srv):
        out = _run(srv.list_audit())
        assert "No audit entries" in out

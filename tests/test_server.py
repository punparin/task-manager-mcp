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


class TestUpdateTaskAutoPromote:
    """Mirror complete_task's side effect for the self case:
    if blocked_by is modified (no explicit status) and the task ends up
    a Backlog task with zero unresolved blockers, promote to Ready."""

    def test_clearing_blockers_promotes_backlog_to_ready(self, srv, tmp_path):
        srv.store.create(title="A", status="Ready")
        srv.store.create(title="B", status="Backlog", blocked_by=["T-001"])
        result = _run(srv.update_task(task_id="T-002", blocked_by="-"))
        assert srv.store.get("T-002").status == "Ready"
        assert "Promoted to Ready: T-002" in result
        # Audit log records the transition.
        entries = read_audit(tmp_path, task_id="T-002")
        assert any(e["new_status"] == "Ready" and e["old_status"] == "Backlog" for e in entries)

    def test_replacing_with_terminal_blockers_promotes(self, srv):
        srv.store.create(title="Done blocker", status="Done")
        srv.store.create(title="Live blocker", status="In Progress")
        srv.store.create(title="Dependent", status="Backlog", blocked_by=["T-002"])
        # Swap the live blocker for the already-done one — task is now unblocked.
        result = _run(srv.update_task(task_id="T-003", blocked_by="T-001"))
        assert srv.store.get("T-003").status == "Ready"
        assert "Promoted to Ready: T-003" in result

    def test_replacing_with_unfinished_blocker_does_not_promote(self, srv):
        srv.store.create(title="Live blocker A", status="In Progress")
        srv.store.create(title="Live blocker B", status="Ready")
        srv.store.create(title="Dependent", status="Backlog", blocked_by=["T-001"])
        result = _run(srv.update_task(task_id="T-003", blocked_by="T-002"))
        assert srv.store.get("T-003").status == "Backlog"
        assert "Promoted to Ready" not in result

    def test_explicit_status_in_same_call_wins(self, srv):
        # Caller deliberately set status=Backlog while clearing blockers —
        # don't second-guess them.
        srv.store.create(title="A", status="Ready")
        srv.store.create(title="B", status="Backlog", blocked_by=["T-001"])
        _run(srv.update_task(task_id="T-002", blocked_by="-", status="Backlog"))
        assert srv.store.get("T-002").status == "Backlog"

    def test_non_backlog_task_is_left_alone(self, srv):
        # Already Ready / In Progress / Blocked / etc. shouldn't be touched.
        srv.store.create(title="A", status="Ready")
        srv.store.create(title="B", status="Blocked", blocked_by=["T-001"])
        _run(srv.update_task(task_id="T-002", blocked_by="-"))
        assert srv.store.get("T-002").status == "Blocked"

    def test_no_promotion_when_blocked_by_unchanged(self, srv, tmp_path):
        # Updating an unrelated field on a Backlog task must NOT
        # speculatively promote it.
        srv.store.create(title="A", status="Backlog")
        _run(srv.update_task(task_id="T-001", priority="P1"))
        assert srv.store.get("T-001").status == "Backlog"
        assert read_audit(tmp_path, task_id="T-001") == []


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


class TestValidateDependencies:
    def test_clean_vault_reports_ok(self, srv):
        srv.store.create(title="A", status="Ready")
        out = _run(srv.validate_dependencies())
        assert "Vault is valid" in out

    def test_flags_missing_blocker(self, srv):
        srv.store.create(title="A")
        # Hand-corrupt the file to reference a nonexistent dep.
        t = srv.store.get("T-001")
        t.blocked_by = ["T-999"]
        srv.store.save(t)

        out = _run(srv.validate_dependencies())
        assert "Graph:" in out
        assert "T-001 references missing task: T-999" in out

    def test_flags_blocked_by_cancelled(self, srv):
        srv.store.create(title="A", status="Cancelled")
        srv.store.create(title="B", blocked_by=["T-001"])
        out = _run(srv.validate_dependencies())
        assert "T-002 blocked_by T-001 is Cancelled" in out

    def test_flags_in_progress_without_assignee(self, srv):
        srv.store.create(title="A", status="In Progress")
        # Strip assignee on disk to simulate a hand-edited frontmatter.
        t = srv.store.get("T-001")
        t.assignee = ""
        srv.store.save(t)

        out = _run(srv.validate_dependencies())
        assert "Workflow:" in out
        assert "T-001 is In Progress but has no assignee" in out

    def test_flags_completed_on_non_done_task(self, srv):
        srv.store.create(title="A", status="Ready")
        srv.store.update("T-001", completed="2026-04-20")
        out = _run(srv.validate_dependencies())
        assert "State drift:" in out
        assert "T-001 has completed=2026-04-20" in out

    def test_cycle_reported_once(self, srv):
        # Build A → B → A by creating B first, then closing the loop on A.
        srv.store.create(title="A")
        srv.store.create(title="B", blocked_by=["T-001"])
        t1 = srv.store.get("T-001")
        t1.blocked_by = ["T-002"]
        srv.store.save(t1)

        out = _run(srv.validate_dependencies())
        assert out.count("Cycle detected") == 1


class TestBulkUpdate:
    def test_applies_updates_in_order(self, srv):
        srv.store.create(title="A", status="Backlog", priority="P3")
        srv.store.create(title="B", status="Backlog", priority="P3")
        result = _run(srv.bulk_update(updates=[
            {"task_id": "T-001", "status": "Ready"},
            {"task_id": "T-002", "priority": "P1", "status": "Ready"},
        ]))
        parsed = json.loads(result)
        assert all(r["ok"] for r in parsed)
        assert srv.store.get("T-001").status == "Ready"
        assert srv.store.get("T-002").priority == "P1"
        assert srv.store.get("T-002").status == "Ready"

    def test_per_entry_failure_does_not_block_others(self, srv):
        srv.store.create(title="A")
        result = _run(srv.bulk_update(updates=[
            {"task_id": "T-001", "priority": "P1"},
            {"task_id": "T-999", "priority": "P2"},  # missing
        ]))
        parsed = json.loads(result)
        assert parsed[0]["ok"] is True
        assert parsed[1]["ok"] is False
        assert srv.store.get("T-001").priority == "P1"

    def test_rejects_unknown_field(self, srv):
        srv.store.create(title="A")
        result = _run(srv.bulk_update(updates=[
            {"task_id": "T-001", "rocket_fuel": "high"},
        ]))
        parsed = json.loads(result)
        assert parsed[0]["ok"] is False
        assert "unknown fields" in parsed[0]["error"]
        assert "rocket_fuel" in parsed[0]["error"]

    def test_missing_task_id_reported_with_index(self, srv):
        result = _run(srv.bulk_update(updates=[{"status": "Ready"}]))
        parsed = json.loads(result)
        assert parsed[0]["ok"] is False
        assert parsed[0]["index"] == 0
        assert "task_id" in parsed[0]["error"]

    def test_invalid_status_surfaces_underlying_error(self, srv):
        srv.store.create(title="A")
        result = _run(srv.bulk_update(updates=[
            {"task_id": "T-001", "status": "Bogus"},
        ]))
        parsed = json.loads(result)
        assert parsed[0]["ok"] is False
        assert "Invalid status" in parsed[0]["error"]


class TestTaskTreeDirection:
    def test_blockers_default(self, srv):
        srv.store.create(title="A", status="Done")
        srv.store.create(title="B", blocked_by=["T-001"])
        result = _run(srv.task_tree(task_id="T-002"))
        assert "T-002" in result
        assert "T-001" in result
        # Default ('blockers') uses the single-tree renderer, no headers.
        assert "Blockers (waiting on)" not in result
        assert "Dependents" not in result

    def test_dependents_only(self, srv):
        srv.store.create(title="A")
        srv.store.create(title="B", blocked_by=["T-001"])
        result = _run(srv.task_tree(task_id="T-001", direction="dependents"))
        assert "T-002" in result
        assert "Dependents" not in result  # single-tree mode

    def test_both_renders_two_sections(self, srv):
        srv.store.create(title="A", status="Done")
        srv.store.create(title="B", blocked_by=["T-001"])
        srv.store.create(title="C", blocked_by=["T-002"])
        result = _run(srv.task_tree(task_id="T-002", direction="both"))
        assert "Blockers (waiting on):" in result
        assert "Dependents (waiting on this):" in result
        assert "T-001" in result  # blocker shown
        assert "T-003" in result  # dependent shown

    def test_both_marks_empty_sides(self, srv):
        srv.store.create(title="solo")
        result = _run(srv.task_tree(task_id="T-001", direction="both"))
        assert "Blockers (waiting on):\n  (none)" in result
        assert "Dependents (waiting on this):\n  (none)" in result

    def test_invalid_direction(self, srv):
        srv.store.create(title="A")
        result = _run(srv.task_tree(task_id="T-001", direction="sideways"))
        assert result.startswith("ERROR:")

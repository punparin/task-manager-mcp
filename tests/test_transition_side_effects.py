"""Side-effect matrix for status transitions.

The pattern this guards against is real: PR #45 added auto-promote to
`complete_task`, but the mirror behavior had to be added later for
`update_task(blocked_by=…)` (#60) and `update_task(status="Cancelled")`
(#63). Each shipped as its own follow-up once the omission was noticed.

This matrix exercises every (from_status, to_status, trigger) combo
together so a future regression on any one path lights up immediately,
and the symmetry between `complete_task` and `update_task(status="Done")`
is enforced rather than hoped for.
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


# Each row: (from_status, trigger, to_status, dep_to_status, dep_blocked_by).
# T-001 starts in `from_status`; T-002 is a dependent blocked solely
# by T-001. After applying `trigger`, T-001 lands in `to_status` and
# T-002 lands in (dep_to_status, dep_blocked_by).
TRANSITIONS_BACKLOG_DEP = [
    pytest.param(
        "Ready", lambda s: s.start_task(task_id="T-001"),
        "In Progress", "Backlog", ["T-001"],
        id="ready->in-progress (start_task)",
    ),
    pytest.param(
        "In Progress", lambda s: s.complete_task(task_id="T-001"),
        "Done", "Ready", ["T-001"],
        id="in-progress->done (complete_task)",
    ),
    pytest.param(
        "In Progress", lambda s: s.update_task(task_id="T-001", status="Done"),
        "Done", "Ready", ["T-001"],
        id="in-progress->done (update_task)",
    ),
    pytest.param(
        "In Progress",
        lambda s: s.bulk_update(updates=[{"task_id": "T-001", "status": "Done"}]),
        "Done", "Ready", ["T-001"],
        id="in-progress->done (bulk_update)",
    ),
    pytest.param(
        "In Progress",
        lambda s: s.block_task(task_id="T-001", reason="external"),
        "Blocked", "Backlog", ["T-001"],
        id="in-progress->blocked (block_task)",
    ),
    pytest.param(
        "Blocked", lambda s: s.update_task(task_id="T-001", status="Ready"),
        "Ready", "Backlog", ["T-001"],
        id="blocked->ready (update_task)",
    ),
    pytest.param(
        "Backlog",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", "Ready", [],
        id="backlog->cancelled (update_task)",
    ),
    pytest.param(
        "Ready",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", "Ready", [],
        id="ready->cancelled (update_task)",
    ),
    pytest.param(
        "In Progress",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", "Ready", [],
        id="in-progress->cancelled (update_task)",
    ),
    pytest.param(
        "In Progress",
        lambda s: s.bulk_update(updates=[{"task_id": "T-001", "status": "Cancelled"}]),
        "Cancelled", "Ready", [],
        id="in-progress->cancelled (bulk_update)",
    ),
    pytest.param(
        "Blocked",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", "Ready", [],
        id="blocked->cancelled (update_task)",
    ),
]


@pytest.mark.parametrize(
    "from_status,trigger,to_status,dep_to_status,dep_blocked_by",
    TRANSITIONS_BACKLOG_DEP,
)
def test_transition_with_backlog_dependent(
    srv, from_status, trigger, to_status, dep_to_status, dep_blocked_by,
):
    """For every transition path, T-002 (Backlog dep blocked solely by
    T-001) must land in the expected (status, blocked_by) state."""
    srv.store.create(title="Trigger", status=from_status)
    srv.store.create(title="Dep", status="Backlog", blocked_by=["T-001"])

    _run(trigger(srv))

    assert srv.store.get("T-001").status == to_status
    assert srv.store.get("T-002").status == dep_to_status
    assert srv.store.get("T-002").blocked_by == dep_blocked_by


# Parallel matrix: a Ready dep (already promoted manually) must never
# get re-promoted, but Cancellation should still strip the dead link.
TRANSITIONS_READY_DEP = [
    pytest.param(
        "In Progress", lambda s: s.complete_task(task_id="T-001"),
        "Done", ["T-001"],
        id="complete_task preserves link on ready dep",
    ),
    pytest.param(
        "In Progress", lambda s: s.update_task(task_id="T-001", status="Done"),
        "Done", ["T-001"],
        id="update_task(Done) preserves link on ready dep",
    ),
    pytest.param(
        "Backlog",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", [],
        id="update_task(Cancelled) strips dead link from ready dep",
    ),
    pytest.param(
        "In Progress",
        lambda s: s.update_task(task_id="T-001", status="Cancelled"),
        "Cancelled", [],
        id="update_task(Cancelled) from in-progress strips dead link",
    ),
]


@pytest.mark.parametrize(
    "from_status,trigger,to_status,dep_blocked_by", TRANSITIONS_READY_DEP,
)
def test_transition_with_ready_dependent(
    srv, from_status, trigger, to_status, dep_blocked_by,
):
    """A Ready dep stays Ready (no double-promote). Only Cancellation
    strips T-001 out of the dep's blocked_by list."""
    srv.store.create(title="Trigger", status=from_status)
    srv.store.create(title="Dep", status="Ready", blocked_by=["T-001"])

    _run(trigger(srv))

    assert srv.store.get("T-001").status == to_status
    assert srv.store.get("T-002").status == "Ready"  # never re-promoted
    assert srv.store.get("T-002").blocked_by == dep_blocked_by


def test_cancellation_strips_only_the_dead_blocker(srv):
    """When T-001 is cancelled, dep blocked by T-001 *and* T-003 keeps
    T-003 in its list and stays Backlog (still has an unfinished
    blocker). Guards against over-eager promotion or list-clobbering."""
    srv.store.create(title="Trigger", status="In Progress")
    srv.store.create(title="Other blocker", status="Ready")
    srv.store.create(title="Dep", status="Backlog", blocked_by=["T-001", "T-002"])

    _run(srv.update_task(task_id="T-001", status="Cancelled"))

    dep = srv.store.get("T-003")
    assert dep.status == "Backlog"
    assert dep.blocked_by == ["T-002"]


def test_done_does_not_strip_link(srv):
    """Symmetric counter-case: Done preserves the dep link as historical
    context. PR #45 was explicit that Done means 'dep was satisfied',
    not 'dep is dead' — so the link must survive."""
    srv.store.create(title="Trigger", status="In Progress")
    srv.store.create(title="Dep", status="Backlog", blocked_by=["T-001"])

    _run(srv.complete_task(task_id="T-001"))

    assert srv.store.get("T-002").blocked_by == ["T-001"]

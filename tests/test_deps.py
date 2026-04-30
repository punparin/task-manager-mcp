from task_manager_mcp.deps import (
    blocked_tasks,
    detect_cycle,
    is_unblocked,
    next_task,
    task_tree,
    what_unblocks,
)


class TestDetectCycle:
    def test_no_cycle(self, store):
        store.create(title="A")
        store.create(title="B", blocked_by=["T-001"])
        assert detect_cycle(store, "T-002", ["T-001"]) is None

    def test_self_cycle(self, store):
        store.create(title="A")
        cycle = detect_cycle(store, "T-001", ["T-001"])
        assert cycle is not None
        assert "T-001" in cycle

    def test_indirect_cycle(self, store):
        store.create(title="A")
        store.create(title="B", blocked_by=["T-001"])
        store.create(title="C", blocked_by=["T-002"])
        # Now if we try to make T-001 blocked_by T-003, we get a cycle
        cycle = detect_cycle(store, "T-001", ["T-003"])
        assert cycle is not None


class TestIsUnblocked:
    def test_no_deps_is_unblocked(self, store):
        store.create(title="A", status="Ready")
        all_tasks = {t.id: t for t in store.all()}
        assert is_unblocked(all_tasks["T-001"], all_tasks)

    def test_blocked_by_unfinished(self, store):
        store.create(title="A", status="Ready")
        store.create(title="B", status="Ready", blocked_by=["T-001"])
        all_tasks = {t.id: t for t in store.all()}
        assert not is_unblocked(all_tasks["T-002"], all_tasks)

    def test_blocked_by_done_is_unblocked(self, store):
        store.create(title="A", status="Done")
        store.create(title="B", status="Ready", blocked_by=["T-001"])
        all_tasks = {t.id: t for t in store.all()}
        assert is_unblocked(all_tasks["T-002"], all_tasks)

    def test_blocked_by_cancelled_is_unblocked(self, store):
        store.create(title="A", status="Cancelled")
        store.create(title="B", status="Ready", blocked_by=["T-001"])
        all_tasks = {t.id: t for t in store.all()}
        assert is_unblocked(all_tasks["T-002"], all_tasks)


class TestNextTask:
    def test_returns_ready_task(self, store):
        store.create(title="A", status="Ready", assignee="claude", priority="P2")
        result = next_task(store, "claude")
        assert result.id == "T-001"

    def test_filters_by_assignee(self, store):
        store.create(title="A", status="Ready", assignee="me")
        result = next_task(store, "claude")
        assert result is None

    def test_skips_blocked(self, store):
        store.create(title="A", status="Ready", assignee="claude")
        store.create(title="B", status="Ready", assignee="claude", blocked_by=["T-001"])
        # T-002 is blocked, T-001 is not
        result = next_task(store, "claude")
        assert result.id == "T-001"

    def test_priority_order(self, store):
        store.create(title="P3 task", status="Ready", assignee="claude", priority="P3")
        store.create(title="P1 task", status="Ready", assignee="claude", priority="P1")
        store.create(title="P2 task", status="Ready", assignee="claude", priority="P2")
        result = next_task(store, "claude")
        assert result.title == "P1 task"

    def test_due_date_order(self, store):
        store.create(title="Late", status="Ready", assignee="claude", priority="P2", due="2026-12-31")
        store.create(title="Soon", status="Ready", assignee="claude", priority="P2", due="2026-04-15")
        result = next_task(store, "claude")
        assert result.title == "Soon"

    def test_no_workable_tasks(self, store):
        store.create(title="A", status="Backlog", assignee="claude")
        assert next_task(store, "claude") is None

    def test_agent_filter_matches_legacy_claude_files(self, store):
        """Querying for 'agent' should match files written with assignee: claude."""
        store.create(title="Legacy", status="Ready", assignee="claude", priority="P2")
        result = next_task(store, "agent")
        assert result is not None
        assert result.title == "Legacy"

    def test_claude_filter_matches_new_agent_files(self, store):
        """Backward direction: querying for 'claude' should match files using 'agent'."""
        store.create(title="New", status="Ready", assignee="agent", priority="P2")
        result = next_task(store, "claude")
        assert result is not None
        assert result.title == "New"

    def test_agent_assignee_is_valid(self, store):
        """create_task with assignee='agent' should succeed (no ValueError)."""
        task = store.create(title="A", status="Ready", assignee="agent")
        assert task.assignee == "agent"


class TestTaskTree:
    def test_simple_tree(self, store):
        store.create(title="A", status="Done")
        store.create(title="B", blocked_by=["T-001"])
        tree = task_tree(store, "T-002")
        assert tree["id"] == "T-002"
        assert len(tree["deps"]) == 1
        assert tree["deps"][0]["id"] == "T-001"

    def test_missing_dep(self, store):
        store.create(title="A", blocked_by=[])
        # Manually corrupt to reference missing
        t = store.get("T-001")
        t.blocked_by = ["T-999"]
        store.save(t)
        tree = task_tree(store, "T-001")
        assert tree["deps"][0]["title"] == "(missing)"


class TestBlockedTasks:
    def test_finds_blocked(self, store):
        store.create(title="A", status="Ready")
        store.create(title="B", status="Ready", blocked_by=["T-001"])
        blocked = blocked_tasks(store)
        assert len(blocked) == 1
        assert blocked[0].id == "T-002"


class TestWhatUnblocks:
    def test_returns_dependents(self, store):
        store.create(title="A", status="In Progress")
        store.create(title="B", status="Ready", blocked_by=["T-001"])
        store.create(title="C", status="Ready", blocked_by=["T-001"])
        unblocked = what_unblocks(store, "T-001")
        ids = [t.id for t in unblocked]
        assert "T-002" in ids
        assert "T-003" in ids

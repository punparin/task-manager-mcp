import pytest

from task_manager_mcp.tasks import Task


class TestTaskValidation:
    def test_valid_task(self):
        t = Task(id="T-001", title="Test", status="Ready", priority="P2", assignee="me")
        assert t.id == "T-001"
        assert t.created  # auto-set

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid status"):
            Task(id="T-001", title="Test", status="Bogus")

    def test_invalid_priority(self):
        with pytest.raises(ValueError, match="Invalid priority"):
            Task(id="T-001", title="Test", priority="P9")

    def test_invalid_assignee(self):
        with pytest.raises(ValueError, match="Invalid assignee"):
            Task(id="T-001", title="Test", assignee="bob")


class TestTaskMarkdown:
    def test_round_trip(self):
        t = Task(
            id="T-042",
            title="Fix bug",
            status="Ready",
            priority="P2",
            assignee="claude",
            tags=["bug", "auth"],
            blocked_by=["T-001"],
            body="## Steps\n1. Fix it",
        )
        md = t.to_markdown()
        t2 = Task.from_markdown(md)
        assert t2.id == "T-042"
        assert t2.title == "Fix bug"
        assert t2.status == "Ready"
        assert t2.tags == ["bug", "auth"]
        assert t2.blocked_by == ["T-001"]
        assert "Fix it" in t2.body


class TestTaskStore:
    def test_create_auto_id(self, store):
        t1 = store.create(title="First")
        t2 = store.create(title="Second")
        assert t1.id == "T-001"
        assert t2.id == "T-002"

    def test_get(self, store):
        store.create(title="My Task", priority="P1")
        t = store.get("T-001")
        assert t.title == "My Task"
        assert t.priority == "P1"

    def test_update(self, store):
        store.create(title="Test")
        t = store.update("T-001", status="In Progress", priority="P1")
        assert t.status == "In Progress"
        assert t.priority == "P1"

    def test_update_done_sets_completed(self, store):
        store.create(title="Test")
        t = store.update("T-001", status="Done")
        assert t.completed  # auto-set

    def test_delete(self, store):
        store.create(title="Test")
        store.delete("T-001")
        assert not store.exists("T-001")

    def test_create_blocked_by_missing_raises(self, store):
        with pytest.raises(ValueError, match="does not exist"):
            store.create(title="Test", blocked_by=["T-999"])

    def test_all_returns_sorted(self, store):
        store.create(title="A")
        store.create(title="B")
        store.create(title="C")
        ids = [t.id for t in store.all()]
        assert ids == ["T-001", "T-002", "T-003"]

import pytest

from task_manager_mcp.tasks import Task, TaskStore


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

    def test_unknown_assignee_loads_from_disk(self, tmp_path):
        # Reads stay permissive: a vault file with an assignee that's no
        # longer in the configured actor list still loads cleanly. (Write
        # validation lives on TaskStore — see TestActorsConfig.)
        t = Task(id="T-001", title="Legacy", assignee="someone-not-configured")
        assert t.assignee == "someone-not-configured"


class TestStoreAssigneeValidation:
    def test_create_rejects_unknown_assignee(self, store):
        with pytest.raises(ValueError, match="Invalid assignee"):
            store.create(title="Test", assignee="bob")

    def test_update_rejects_unknown_assignee(self, store):
        store.create(title="Test")
        with pytest.raises(ValueError, match="Invalid assignee"):
            store.update("T-001", assignee="bob")

    def test_create_accepts_default_actors(self, store):
        for a in ("me", "agent", "claude"):
            t = store.create(title=f"For {a}", assignee=a)
            assert t.assignee == a


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


class TestTasksFolder:
    """The folder where task files live is configurable so teams can fit
    the MCP into their existing vault layout (e.g. tasks live under
    `inbox/tasks/` or `work/queue/`)."""

    def test_default_folder_is_tasks(self, tmp_path):
        from task_manager_mcp.tasks import TaskStore

        store = TaskStore(tmp_path)
        assert store.tasks_dir == (tmp_path / "tasks").resolve()

    def test_constructor_arg_overrides_default(self, tmp_path):
        from task_manager_mcp.tasks import TaskStore

        store = TaskStore(tmp_path, tasks_folder="work/queue")
        assert store.tasks_dir == (tmp_path / "work" / "queue").resolve()
        store.create(title="Custom-folder task")
        assert (tmp_path / "work" / "queue" / "T-001.md").exists()

    def test_env_var_picked_up_when_no_arg(self, tmp_path, monkeypatch):
        from task_manager_mcp.tasks import TaskStore

        monkeypatch.setenv("TASK_MANAGER_TASKS_FOLDER", "inbox/tasks")
        store = TaskStore(tmp_path)
        assert store.tasks_dir == (tmp_path / "inbox" / "tasks").resolve()

    def test_constructor_arg_beats_env_var(self, tmp_path, monkeypatch):
        from task_manager_mcp.tasks import TaskStore

        monkeypatch.setenv("TASK_MANAGER_TASKS_FOLDER", "from-env")
        store = TaskStore(tmp_path, tasks_folder="from-arg")
        assert store.tasks_dir == (tmp_path / "from-arg").resolve()

    def test_path_traversal_rejected(self, tmp_path):
        from task_manager_mcp.tasks import TaskStore

        with pytest.raises(ValueError, match="outside vault"):
            TaskStore(tmp_path, tasks_folder="../escape")


class TestActorsConfig:
    """Teams can declare a custom actor list at
    `<vault>/.task-manager/config.yml` so the assignee picker reflects
    real teammates / AI agents instead of hardcoded `me`/`agent`."""

    def _write_config(self, vault_path, body: str):
        cfg_dir = vault_path / ".task-manager"
        cfg_dir.mkdir()
        (cfg_dir / "config.yml").write_text(body, encoding="utf-8")

    def test_default_actors_when_no_config(self, tmp_path):
        store = TaskStore(tmp_path)
        assert store.actors == ["me", "agent", "claude"]

    def test_custom_actors_from_config(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - me\n  - agent\n  - alice\n  - bob\n")
        store = TaskStore(tmp_path)
        assert store.actors == ["me", "agent", "alice", "bob"]

    def test_custom_actor_accepted_on_create(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - me\n  - alice\n")
        store = TaskStore(tmp_path)
        t = store.create(title="Onboard new dev", assignee="alice")
        assert t.assignee == "alice"

    def test_default_actor_rejected_when_not_in_custom_list(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - alice\n  - bob\n")
        store = TaskStore(tmp_path)
        with pytest.raises(ValueError, match="Invalid assignee"):
            store.create(title="x", assignee="me")

    def test_claude_alias_kept_when_agent_in_custom_list(self, tmp_path):
        # Old vaults might have files with `assignee: claude` already.
        # If `agent` is in the team's actor list, `claude` should still
        # be writable so those files round-trip cleanly.
        self._write_config(tmp_path, "actors:\n  - alice\n  - agent\n")
        store = TaskStore(tmp_path)
        t = store.create(title="legacy", assignee="claude")
        assert t.assignee == "claude"

    def test_claude_rejected_when_agent_not_in_custom_list(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - alice\n  - bob\n")
        store = TaskStore(tmp_path)
        with pytest.raises(ValueError, match="Invalid assignee"):
            store.create(title="x", assignee="claude")

    def test_malformed_yaml_raises(self, tmp_path):
        self._write_config(tmp_path, "actors: [unclosed\n")
        with pytest.raises(ValueError, match="failed to parse"):
            TaskStore(tmp_path)

    def test_missing_actors_key_raises(self, tmp_path):
        self._write_config(tmp_path, "tasks_folder: tasks\n")
        with pytest.raises(ValueError, match="actors"):
            TaskStore(tmp_path)

    def test_empty_actors_list_raises(self, tmp_path):
        self._write_config(tmp_path, "actors: []\n")
        with pytest.raises(ValueError, match="non-empty"):
            TaskStore(tmp_path)

    def test_non_string_actor_raises(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - me\n  - 42\n")
        with pytest.raises(ValueError, match="non-empty string"):
            TaskStore(tmp_path)

    def test_duplicate_actors_deduped(self, tmp_path):
        self._write_config(tmp_path, "actors:\n  - me\n  - alice\n  - me\n")
        store = TaskStore(tmp_path)
        assert store.actors == ["me", "alice"]

    def test_existing_task_with_unconfigured_assignee_still_loads(self, tmp_path):
        # Bootstrap the store with default actors so we can write a task
        # for `claude`, then re-init with a config that drops `claude`
        # entirely. The old task file should still load on read.
        store = TaskStore(tmp_path)
        store.create(title="Legacy task", assignee="claude")
        self._write_config(tmp_path, "actors:\n  - alice\n  - bob\n")
        store2 = TaskStore(tmp_path)
        loaded = store2.get("T-001")
        assert loaded.assignee == "claude"

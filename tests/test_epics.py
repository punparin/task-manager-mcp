"""Epics: file format, store, derived progress, and the MCP tools."""

from __future__ import annotations

import asyncio
import importlib
import json
from datetime import date, timedelta

import pytest

from task_manager_mcp.audit import read_audit
from task_manager_mcp.epics import Epic, EpicStore, epic_body, epic_progress
from task_manager_mcp.tasks import Task, TaskStore


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    import task_manager_mcp.server as server_module
    importlib.reload(server_module)
    server_module.store = TaskStore(tmp_path)
    return server_module


def _run(coro):
    return asyncio.run(coro)


def _json_after_header(text: str):
    # Tool replies are "Created E-001: ...\n{json}" (plus optional notes).
    return json.JSONDecoder().raw_decode(text[text.index("{"):])[0]


# ── Model and store ────────────────────────────────────────────────────


class TestEpicFile:
    def test_round_trip(self):
        e = Epic(
            id="E-001", title="API v3", status="Active", priority="P1",
            project="[[API]]", due="2026-12-31", color="sky", tags=["backend"],
            body="## Goal\nShip it",
        )
        back = Epic.from_markdown(e.to_markdown())
        assert back == e
        assert "type: epic" in e.to_markdown()

    def test_rejects_task_statuses_and_bad_colours(self):
        with pytest.raises(ValueError):
            Epic(id="E-001", title="x", status="In Progress")
        with pytest.raises(ValueError):
            Epic(id="E-001", title="x", color="mauve")

    def test_colour_picked_by_id_when_unset(self):
        assert Epic(id="E-001", title="a").resolved_color == "#a78bfa"
        assert Epic(id="E-002", title="b").resolved_color == "#fbbf24"
        assert Epic(id="E-009", title="c").resolved_color == "#a78bfa"
        assert Epic(id="E-002", title="d", color="#123456").resolved_color == "#123456"

    def test_body_template(self):
        body = epic_body("Why", "First\n- [ ] Second\n\n- Third")
        assert body == (
            "## Goal\nWhy\n\n"
            "## Success criteria\n- [ ] First\n- [ ] Second\n- [ ] Third\n"
        )


class TestEpicStore:
    def test_ids_and_shared_folder(self, store):
        epics = EpicStore(store)
        assert epics.create(title="One").id == "E-001"
        assert epics.create(title="Two").id == "E-002"
        store.create(title="A task")
        # Epic files sit next to tasks but never show up as tasks.
        assert [t.id for t in store.all()] == ["T-001"]
        assert [e.id for e in epics.all()] == ["E-001", "E-002"]
        assert store.next_id() == "T-002"

    def test_epic_ids_are_not_tasks(self, store):
        EpicStore(store).create(title="One")
        assert not store.exists("E-001")
        with pytest.raises(FileNotFoundError):
            store.get("E-001")
        with pytest.raises(ValueError):
            store.create(title="x", blocked_by=["E-001"])

    def test_task_epic_must_exist(self, store):
        with pytest.raises(ValueError, match="Epic not found"):
            store.create(title="x", epic="E-404")
        EpicStore(store).create(title="One")
        t = store.create(title="x", epic="E-001")
        assert store.get(t.id).epic == "E-001"
        assert store.update(t.id, epic=None).epic is None


class TestProgress:
    def _tasks(self, *statuses):
        return [Task(id=f"T-{i:03d}", title="t", status=s, epic="E-001")
                for i, s in enumerate(statuses, 1)]

    def test_rollup_skips_cancelled(self):
        e = Epic(id="E-001", title="x", status="Active")
        p = epic_progress(e, self._tasks("Done", "Done", "Ready", "Blocked", "Cancelled"))
        assert (p["done"], p["total"], p["pct"], p["cancelled"], p["blocked"]) == (2, 4, 50, 1, 1)
        assert p["by_status"] == {"Done": 2, "Ready": 1, "Blocked": 1, "Cancelled": 1}
        assert not p["ready_to_close"]

    def test_ready_to_close_is_only_a_hint_for_open_epics(self):
        tasks = self._tasks("Done", "Cancelled")
        assert epic_progress(Epic(id="E-001", title="x", status="Active"), tasks)["ready_to_close"]
        assert not epic_progress(Epic(id="E-001", title="x", status="Done"), tasks)["ready_to_close"]
        # An epic with no tasks yet isn't "finished".
        assert not epic_progress(Epic(id="E-001", title="x", status="Active"), [])["ready_to_close"]

    def test_overdue(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        assert epic_progress(Epic(id="E-001", title="x", status="Active", due=past), [])["overdue"]
        assert not epic_progress(Epic(id="E-001", title="x", status="Done", due=past), [])["overdue"]


# ── MCP tools ──────────────────────────────────────────────────────────


class TestEpicTools:
    def test_create_and_get(self, srv):
        out = _run(srv.create_epic(
            title="Big goal", goal="Why it matters",
            success_criteria="Thing one\nThing two", priority="P1", status="Active",
        ))
        assert out.startswith("Created E-001: Big goal")
        _run(srv.create_task(title="Do A", epic="E-001", status="Ready", assignee="agent"))
        _run(srv.create_task(title="Do B", epic="E-001"))
        _run(srv.create_task(title="Unrelated"))
        srv.store.update("T-002", status="Done")

        got = json.loads(_run(srv.get_epic("E-001")))
        assert got["progress"]["done"] == 1 and got["progress"]["total"] == 2
        assert got["criteria"]["total"] == 2
        assert [t["id"] for t in got["tasks"]["Ready"]] == ["T-001"]
        assert [t["id"] for t in got["tasks"]["Done"]] == ["T-002"]
        assert got["next_task"]["id"] == "T-001"

    def test_create_rejects_bad_input(self, srv):
        assert _run(srv.create_epic(title="x", status="Done")).startswith("ERROR")
        assert _run(srv.create_epic(title="x", color="mauve")).startswith("ERROR")
        assert _run(srv.create_task(title="x", epic="E-404")).startswith("ERROR")

    def test_list_filters_and_sorts(self, srv):
        _run(srv.create_epic(title="Later", status="Planned"))
        _run(srv.create_epic(title="Now", status="Active", priority="P2"))
        _run(srv.create_epic(title="Urgent", status="Active", priority="P1"))
        _run(srv.update_epic("E-001", status="Cancelled"))
        ids = [e["id"] for e in json.loads(_run(srv.list_epics()))]
        assert ids == ["E-003", "E-002", "E-001"]
        assert [e["id"] for e in json.loads(_run(srv.list_epics(status="open")))] == ["E-003", "E-002"]
        assert _run(srv.list_epics(status="Done")) == "No epics match those filters."
        assert _run(srv.list_epics(status="bogus")).startswith("ERROR")

    def test_list_tasks_epic_filter(self, srv):
        _run(srv.create_epic(title="E"))
        _run(srv.create_task(title="in", epic="E-001"))
        _run(srv.create_task(title="out"))
        assert [t["id"] for t in json.loads(_run(srv.list_tasks(epic="e-001")))] == ["T-001"]
        assert [t["id"] for t in json.loads(_run(srv.list_tasks(epic="none")))] == ["T-002"]

    def test_update_task_moves_and_clears_epic(self, srv):
        _run(srv.create_epic(title="One"))
        _run(srv.create_epic(title="Two"))
        _run(srv.create_task(title="t", epic="E-001"))
        _run(srv.update_task("T-001", epic="E-002"))
        assert srv.store.get("T-001").epic == "E-002"
        _run(srv.update_task("T-001", epic="-"))
        assert srv.store.get("T-001").epic is None
        assert _run(srv.update_task("T-001", epic="E-404")).startswith("ERROR")

    def test_bulk_update_accepts_epic(self, srv):
        _run(srv.create_epic(title="One"))
        _run(srv.create_task(title="a"))
        _run(srv.create_task(title="b"))
        res = json.loads(_run(srv.bulk_update([
            {"task_id": "T-001", "epic": "E-001"},
            {"task_id": "T-002", "epic": "E-404"},
        ])))
        assert res[0]["ok"] and not res[1]["ok"]
        assert srv.store.get("T-001").epic == "E-001"

    def test_filing_under_closed_epic_warns_but_works(self, srv):
        _run(srv.create_epic(title="Old"))
        _run(srv.update_epic("E-001", status="Done"))
        out = _run(srv.create_task(title="follow-up", epic="E-001"))
        assert "Created T-001" in out and "E-001 (Old) is Done" in out

    def test_close_leaves_tasks_alone_and_lists_them(self, srv):
        _run(srv.create_epic(title="E", status="Active"))
        _run(srv.create_task(title="open one", epic="E-001", status="Ready"))
        out = _run(srv.update_epic("E-001", status="Cancelled"))
        assert "still open and were left unchanged: T-001 (Ready)" in out
        assert srv.store.get("T-001").status == "Ready"

    def test_status_change_stamps_completed_and_audit(self, srv):
        _run(srv.create_epic(title="E"))
        done = _json_after_header(_run(srv.update_epic("E-001", status="Done")))
        assert done["completed"] == date.today().isoformat()
        reopened = _json_after_header(_run(srv.update_epic("E-001", status="Active")))
        assert reopened["completed"] is None
        log = read_audit(srv.store.vault, task_id="E-001")
        assert [(e["old_status"], e["new_status"]) for e in log] == [
            ("Done", "Active"), ("Planned", "Done"),
        ]

    def test_update_clears_optional_fields(self, srv):
        _run(srv.create_epic(title="E", project="[[P]]", due="2027-01-01", color="sky", tags="a,b"))
        _run(srv.update_epic("E-001", project="-", due="-", color="-", tags="-", title="Renamed"))
        e = EpicStore(srv.store).get("E-001")
        assert (e.title, e.project, e.due, e.color, e.tags) == ("Renamed", None, None, None, [])
        assert _run(srv.update_epic("E-404", title="x")).startswith("ERROR")
        assert _run(srv.update_epic("E-001", status="Ready")).startswith("ERROR")

    def test_next_task_scoped_to_epic(self, srv):
        _run(srv.create_epic(title="E"))
        _run(srv.create_task(title="outside", status="Ready", assignee="agent", priority="P1"))
        _run(srv.create_task(title="inside", status="Ready", assignee="agent", epic="E-001"))
        assert json.loads(_run(srv.next_task()))["id"] == "T-001"
        assert json.loads(_run(srv.next_task(epic="E-001")))["id"] == "T-002"

    def test_tick_item_on_epic_criteria(self, srv):
        _run(srv.create_epic(title="E", success_criteria="one\ntwo"))
        out = _run(srv.tick_item("E-001", 2))
        assert "checked item 2 of E-001: two" in out
        assert "- [x] two" in EpicStore(srv.store).get("E-001").body

    def test_validate_dependencies_flags_epic_issues(self, srv):
        _run(srv.create_epic(title="E", status="Active"))
        _run(srv.create_task(title="open", epic="E-001"))
        _run(srv.update_epic("E-001", status="Done"))
        t = srv.store.get("T-001")
        t.epic = "E-404"  # simulate a hand edit pointing at a deleted epic
        srv.store.save(t)
        _run(srv.create_task(title="still open", epic="E-001"))
        out = _run(srv.validate_dependencies())
        assert "T-001 references missing epic: E-404" in out
        assert "E-001 is Done but has open tasks: T-002" in out

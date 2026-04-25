"""Tests for the FastAPI explorer sidecar."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from task_manager_mcp.explorer.server import create_app
from task_manager_mcp.tasks import TaskStore


@pytest.fixture
def vault(tmp_path):
    """Seed a vault with a small set of tasks covering the interesting cases."""
    store = TaskStore(tmp_path)
    # T-001 Done — used as a satisfied dep
    t1 = store.create(title="Refactor auth", status="Backlog", priority="P2", assignee="claude")
    t1.status = "Done"
    t1.completed = "2026-04-20"
    store.save(t1)

    # T-002 In Progress
    store.create(title="Upgrade Redis", status="In Progress", priority="P2", assignee="claude")

    # T-003 Ready, no deps — should be next_task for claude
    store.create(title="Write CI config", status="Ready", priority="P1", assignee="claude")

    # T-004 Ready but blocked by T-002 (still In Progress) — should appear as ⛔
    store.create(
        title="Implement rate limiting",
        status="Ready",
        priority="P2",
        assignee="claude",
        blocked_by=["T-002"],
    )

    # T-005 Backlog assigned to me
    store.create(title="Plan vacation", status="Backlog", priority="P3", assignee="me")
    return tmp_path


@pytest.fixture
def client(vault):
    return TestClient(create_app(vault))


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["task_count"] == 5
    assert "Backlog" in body["valid_status"]
    # vault_name is exposed for the frontend's URL builder; null when unset
    assert body["vault_name"] is None


def test_health_with_vault_name(vault):
    """When vault_name is passed, /api/health surfaces it so the frontend
    can build portable obsidian://open?vault=<name>&file=<rel> URLs."""
    app = create_app(vault, vault_name="MyVault")
    res = TestClient(app).get("/api/health")
    assert res.json()["vault_name"] == "MyVault"


def test_list_tasks_returns_all_with_payload_fields(client):
    res = client.get("/api/tasks")
    assert res.status_code == 200
    body = res.json()
    assert len(body["tasks"]) == 5
    sample = body["tasks"][0]
    for field in ("id", "title", "status", "priority", "is_unblocked", "unfinished_blockers", "dep_count"):
        assert field in sample


def test_list_tasks_filter_by_assignee(client):
    res = client.get("/api/tasks?assignee=me")
    assert res.status_code == 200
    body = res.json()
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["assignee"] == "me"


def test_next_task_id_is_unblocked_priority_winner(client):
    res = client.get("/api/tasks?assignee=claude")
    body = res.json()
    # T-003 is P1 Ready with no blockers; T-004 is P2 Ready blocked by T-002.
    assert body["next_task_id"] == "T-003"


def test_blocked_task_payload_carries_unfinished_blockers(client):
    res = client.get("/api/tasks/T-004")
    body = res.json()
    assert body["is_unblocked"] is False
    assert body["unfinished_blockers"] == ["T-002"]
    assert body["dep_count"] == 1


def test_status_patch_drag_to_in_progress_validates_blockers(client):
    """Dragging a Ready-but-blocked card to 'In Progress' should fail."""
    res = client.patch("/api/tasks/T-004/status", json={"status": "In Progress"})
    assert res.status_code == 409
    assert "blocked by" in res.json()["detail"]


def test_status_patch_to_done_returns_unblocked_list(client):
    """Completing T-002 should unblock T-004."""
    res = client.patch("/api/tasks/T-002/status", json={"status": "Done"})
    assert res.status_code == 200
    body = res.json()
    assert body["task"]["status"] == "Done"
    assert body["task"]["completed"]  # auto-stamped
    assert "T-004" in body["unblocked"]


def test_status_patch_invalid_status_rejected(client):
    res = client.patch("/api/tasks/T-001/status", json={"status": "Bogus"})
    assert res.status_code == 422


def test_status_patch_unknown_task_404(client):
    res = client.patch("/api/tasks/T-999/status", json={"status": "Ready"})
    assert res.status_code == 404


def test_status_patch_simple_lane_change_no_validation(client):
    """Backlog → Ready is just a status flip; no dep gating."""
    res = client.patch("/api/tasks/T-005/status", json={"status": "Ready"})
    assert res.status_code == 200
    assert res.json()["task"]["status"] == "Ready"


def test_get_task_returns_body_and_tree(client):
    res = client.get("/api/tasks/T-004")
    body = res.json()
    assert "body" in body
    assert "tree" in body
    assert body["tree"]["id"] == "T-004"
    assert any(d["id"] == "T-002" for d in body["tree"]["deps"])


def test_create_task(client):
    res = client.post(
        "/api/tasks",
        json={"title": "New work", "priority": "P2", "assignee": "claude"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "New work"
    assert body["id"].startswith("T-")


def test_create_task_invalid_priority(client):
    res = client.post(
        "/api/tasks",
        json={"title": "Bad", "priority": "P9"},
    )
    assert res.status_code == 422


def test_graph_shape(client):
    res = client.get("/api/graph")
    body = res.json()
    assert "nodes" in body and "edges" in body
    # Five tasks → five nodes
    assert len(body["nodes"]) == 5
    # T-004 → T-002 is the only edge
    assert any(e["data"]["source"] == "T-004" and e["data"]["target"] == "T-002" for e in body["edges"])


def test_blocked_endpoint_returns_ready_blocked(client):
    res = client.get("/api/blocked")
    body = res.json()
    ids = {t["id"] for t in body["tasks"]}
    assert ids == {"T-004"}


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "<title>Task Manager Explorer</title>" in res.text

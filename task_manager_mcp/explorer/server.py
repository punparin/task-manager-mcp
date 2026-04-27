"""FastAPI sidecar for visualizing and managing tasks via a browser."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..checklist import task_to_dict as _task_to_dict
from ..checklist import tick as _tick
from ..deps import blocked_tasks as _blocked_tasks
from ..deps import is_unblocked, what_unblocks
from ..deps import next_task as _next_task
from ..deps import task_tree as _task_tree
from ..tasks import VALID_ASSIGNEE, VALID_PRIORITY, VALID_STATUS, TaskStore

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("task_manager_mcp.explorer")

STATIC_DIR = Path(__file__).parent / "static"


def _package_version() -> str:
    """Resolve installed package version, fall back to 'dev' for non-installed checkouts."""
    try:
        return metadata.version("task-manager-mcp")
    except metadata.PackageNotFoundError:
        return "dev"


class StatusUpdate(BaseModel):
    status: str
    completion_notes: str = ""


class ChecklistTick(BaseModel):
    checked: bool = True


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    project: Optional[str] = None
    area: Optional[str] = None
    due: Optional[str] = None
    tags: Optional[list[str]] = None
    body: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    priority: str = "P3"
    assignee: str = "me"
    status: str = "Backlog"
    project: str = ""
    area: str = ""
    due: str = ""
    tags: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    body: str = ""


def create_app(vault_path: str | Path) -> FastAPI:
    """Build the FastAPI app bound to a vault path. Factored out for tests."""
    store = TaskStore(vault_path)
    app = FastAPI(title="Task Manager Explorer", version="0.1.0")

    # ── Helpers ────────────────────────────────────────────────────────

    def _task_payload(task, all_tasks: dict) -> dict:
        # Pull `progress` from the body for free; helper omits the key when
        # there are no checkboxes so cards stay clean.
        d = _task_to_dict(task)
        unblocked = is_unblocked(task, all_tasks)
        unfinished = [
            dep
            for dep in task.blocked_by
            if dep in all_tasks and all_tasks[dep].status not in {"Done", "Cancelled"}
        ]
        d["is_unblocked"] = unblocked
        d["unfinished_blockers"] = unfinished
        d["dep_count"] = len(task.blocked_by)
        return d

    # ── Health / index ────────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        all_tasks = store.all()
        return {
            "ok": True,
            "vault": str(store.vault),
            "tasks_dir": str(store.tasks_dir),
            "task_count": len(all_tasks),
            "valid_status": VALID_STATUS,
            "valid_priority": VALID_PRIORITY,
            "valid_assignee": VALID_ASSIGNEE,
            "version": _package_version(),
        }

    @app.get("/")
    def index():
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(500, f"index.html missing at {index_path}")
        return FileResponse(index_path)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ── Tasks: list / detail / next / graph ───────────────────────────

    @app.get("/api/tasks")
    def list_tasks(
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
        project: Optional[str] = None,
        area: Optional[str] = None,
    ):
        all_list = store.all()
        all_tasks = {t.id: t for t in all_list}
        results = all_list
        if status:
            results = [t for t in results if t.status == status]
        if assignee:
            results = [t for t in results if t.assignee == assignee]
        if priority:
            results = [t for t in results if t.priority == priority]
        if project:
            results = [t for t in results if t.project and project.lower() in t.project.lower()]
        if area:
            results = [t for t in results if t.area and area.lower() in t.area.lower()]

        next_t = _next_task(store, assignee=assignee or None)
        next_id = next_t.id if next_t else None

        return {
            "tasks": [_task_payload(t, all_tasks) for t in results],
            "next_task_id": next_id,
        }

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        try:
            task = store.get(task_id)
        except FileNotFoundError:
            raise HTTPException(404, f"Task not found: {task_id}")
        all_tasks = {t.id: t for t in store.all()}
        out = _task_payload(task, all_tasks)
        out["body"] = task.body
        out["tree"] = _task_tree(store, task_id)
        return out

    @app.get("/api/next")
    def next_task(assignee: str = "claude"):
        task = _next_task(store, assignee=assignee or None)
        if not task:
            return {"task": None}
        all_tasks = {t.id: t for t in store.all()}
        return {"task": _task_payload(task, all_tasks)}

    @app.get("/api/graph")
    def graph():
        """Dep graph data shaped for Cytoscape.js."""
        all_list = store.all()
        all_tasks = {t.id: t for t in all_list}
        nodes = [
            {
                "data": {
                    "id": t.id,
                    "label": f"{t.id}\n{t.title[:30]}",
                    "status": t.status,
                    "priority": t.priority,
                    "is_unblocked": is_unblocked(t, all_tasks),
                }
            }
            for t in all_list
        ]
        edges = []
        for t in all_list:
            for dep in t.blocked_by:
                if dep in all_tasks:
                    edges.append({"data": {"source": t.id, "target": dep, "id": f"{t.id}->{dep}"}})
        return {"nodes": nodes, "edges": edges}

    @app.get("/api/blocked")
    def blocked():
        """Ready tasks waiting on unfinished deps."""
        all_tasks = {t.id: t for t in store.all()}
        return {"tasks": [_task_payload(t, all_tasks) for t in _blocked_tasks(store)]}

    # ── Tasks: mutations ──────────────────────────────────────────────

    @app.patch("/api/tasks/{task_id}/status")
    def update_status(task_id: str, payload: StatusUpdate):
        try:
            task = store.get(task_id)
        except FileNotFoundError:
            raise HTTPException(404, f"Task not found: {task_id}")
        if payload.status not in VALID_STATUS:
            raise HTTPException(422, f"Invalid status. Must be one of {VALID_STATUS}")

        all_tasks = {t.id: t for t in store.all()}

        # Mirror the MCP semantics: starting a task validates deps.
        if payload.status == "In Progress" and not is_unblocked(task, all_tasks):
            unfinished = [
                d
                for d in task.blocked_by
                if d in all_tasks and all_tasks[d].status not in {"Done", "Cancelled"}
            ]
            raise HTTPException(
                409,
                f"Cannot start {task_id} — blocked by: {', '.join(unfinished)}",
            )

        old_status = task.status
        task.status = payload.status
        unblocked_ids: list[str] = []

        if payload.status == "Done":
            if not task.completed:
                task.completed = date.today().isoformat()
            if payload.completion_notes:
                task.body = (task.body or "").rstrip() + (
                    f"\n\n## Completion Notes\n{payload.completion_notes}\n"
                )
            store.save(task)
            unblocked_ids = [t.id for t in what_unblocks(store, task_id)]
        else:
            store.save(task)

        all_tasks = {t.id: t for t in store.all()}
        return {
            "task": _task_payload(task, all_tasks),
            "old_status": old_status,
            "unblocked": unblocked_ids,
        }

    @app.patch("/api/tasks/{task_id}/checklist/{index}")
    def tick_checklist(task_id: str, index: int, payload: ChecklistTick):
        """Flip the n-th checkbox in the body (1-based). Mirrors MCP tick_item."""
        try:
            task = store.get(task_id)
        except FileNotFoundError:
            raise HTTPException(404, f"Task not found: {task_id}")
        try:
            new_body, _progress = _tick(task.body, index, payload.checked)
        except ValueError as e:
            raise HTTPException(422, str(e))
        task.body = new_body
        store.save(task)
        all_tasks = {t.id: t for t in store.all()}
        out = _task_payload(task, all_tasks)
        out["body"] = task.body
        return out

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: str, payload: TaskUpdate):
        try:
            store.get(task_id)
        except FileNotFoundError:
            raise HTTPException(404, f"Task not found: {task_id}")

        updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
        if "priority" in updates and updates["priority"] not in VALID_PRIORITY:
            raise HTTPException(422, f"Invalid priority. Must be one of {VALID_PRIORITY}")
        if "assignee" in updates and updates["assignee"] not in VALID_ASSIGNEE:
            raise HTTPException(422, f"Invalid assignee. Must be one of {VALID_ASSIGNEE}")

        try:
            task = store.update(task_id, **updates)
        except ValueError as e:
            raise HTTPException(422, str(e))

        all_tasks = {t.id: t for t in store.all()}
        out = _task_payload(task, all_tasks)
        out["body"] = task.body
        return out

    @app.post("/api/tasks")
    def create_task(payload: TaskCreate):
        if payload.priority not in VALID_PRIORITY:
            raise HTTPException(422, f"Invalid priority. Must be one of {VALID_PRIORITY}")
        if payload.assignee not in VALID_ASSIGNEE:
            raise HTTPException(422, f"Invalid assignee. Must be one of {VALID_ASSIGNEE}")
        if payload.status not in VALID_STATUS:
            raise HTTPException(422, f"Invalid status. Must be one of {VALID_STATUS}")
        try:
            task = store.create(
                title=payload.title,
                priority=payload.priority,
                assignee=payload.assignee,
                status=payload.status,
                project=payload.project or None,
                area=payload.area or None,
                due=payload.due or None,
                tags=payload.tags,
                blocked_by=payload.blocked_by,
                body=payload.body,
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

        all_tasks = {t.id: t for t in store.all()}
        out = _task_payload(task, all_tasks)
        out["body"] = task.body
        return out

    return app


def main():
    parser = argparse.ArgumentParser(description="Task Manager Explorer")
    parser.add_argument(
        "--vault",
        default=os.environ.get("OBSIDIAN_VAULT_PATH"),
        help="Vault path (defaults to $OBSIDIAN_VAULT_PATH)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not args.vault:
        logger.error("vault path required: pass --vault or set OBSIDIAN_VAULT_PATH")
        sys.exit(1)

    import uvicorn

    app = create_app(args.vault)
    logger.info("explorer serving %s on http://%s:%d", args.vault, args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

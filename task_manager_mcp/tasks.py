"""Task dataclass, status enums, and file I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import frontmatter

VALID_STATUS = ["Backlog", "Ready", "In Progress", "Done", "Blocked", "Cancelled"]
VALID_PRIORITY = ["P1", "P2", "P3", "P4"]
VALID_ASSIGNEE = ["me", "claude"]

TASK_ID_RE = re.compile(r"^T-(\d+)$")
TASKS_FOLDER = "tasks"


@dataclass
class Task:
    id: str
    title: str
    status: str = "Backlog"
    priority: str = "P3"
    assignee: str = "me"
    project: Optional[str] = None
    area: Optional[str] = None
    due: Optional[str] = None
    created: str = ""
    completed: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    body: str = ""

    def __post_init__(self):
        if self.status not in VALID_STATUS:
            raise ValueError(f"Invalid status: {self.status}. Must be one of {VALID_STATUS}")
        if self.priority not in VALID_PRIORITY:
            raise ValueError(f"Invalid priority: {self.priority}. Must be one of {VALID_PRIORITY}")
        if self.assignee not in VALID_ASSIGNEE:
            raise ValueError(f"Invalid assignee: {self.assignee}. Must be one of {VALID_ASSIGNEE}")
        if not self.created:
            self.created = date.today().isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("body", None)
        return d

    def to_markdown(self) -> str:
        post = frontmatter.Post(self.body or "")
        post.metadata["type"] = "task"
        post.metadata["id"] = self.id
        post.metadata["title"] = self.title
        post.metadata["status"] = self.status
        post.metadata["priority"] = self.priority
        post.metadata["assignee"] = self.assignee
        if self.project:
            post.metadata["project"] = self.project
        if self.area:
            post.metadata["area"] = self.area
        post.metadata["created"] = self.created
        if self.due:
            post.metadata["due"] = self.due
        if self.completed:
            post.metadata["completed"] = self.completed
        if self.tags:
            post.metadata["tags"] = self.tags
        if self.blocked_by:
            post.metadata["blocked_by"] = self.blocked_by
        return frontmatter.dumps(post)

    @classmethod
    def from_markdown(cls, content: str) -> "Task":
        post = frontmatter.loads(content)
        m = post.metadata
        return cls(
            id=str(m.get("id", "")),
            title=str(m.get("title", "")),
            status=str(m.get("status", "Backlog")),
            priority=str(m.get("priority", "P3")),
            assignee=str(m.get("assignee", "me")),
            project=m.get("project"),
            area=m.get("area"),
            due=str(m["due"]) if m.get("due") else None,
            created=str(m.get("created", "")),
            completed=str(m["completed"]) if m.get("completed") else None,
            tags=list(m.get("tags") or []),
            blocked_by=list(m.get("blocked_by") or []),
            body=post.content,
        )


class TaskStore:
    """File-backed task store. Stores tasks as markdown files in tasks/ folder."""

    def __init__(self, vault_path: str | Path):
        self.vault = Path(vault_path).resolve()
        self.tasks_dir = self.vault / TASKS_FOLDER
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.md"

    def next_id(self) -> str:
        """Generate next task ID by scanning existing tasks."""
        max_n = 0
        for f in self.tasks_dir.glob("T-*.md"):
            m = TASK_ID_RE.match(f.stem)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"T-{max_n + 1:03d}"

    def all(self) -> list[Task]:
        tasks = []
        for f in sorted(self.tasks_dir.glob("T-*.md")):
            try:
                tasks.append(Task.from_markdown(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return tasks

    def get(self, task_id: str) -> Task:
        path = self._path_for(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Task not found: {task_id}")
        return Task.from_markdown(path.read_text(encoding="utf-8"))

    def save(self, task: Task) -> None:
        path = self._path_for(task.id)
        path.write_text(task.to_markdown(), encoding="utf-8")

    def delete(self, task_id: str) -> None:
        path = self._path_for(task_id)
        if path.exists():
            path.unlink()

    def exists(self, task_id: str) -> bool:
        return self._path_for(task_id).exists()

    def create(
        self,
        title: str,
        priority: str = "P3",
        assignee: str = "me",
        status: str = "Backlog",
        project: Optional[str] = None,
        area: Optional[str] = None,
        due: Optional[str] = None,
        tags: Optional[list[str]] = None,
        blocked_by: Optional[list[str]] = None,
        body: str = "",
    ) -> Task:
        # Validate blocked_by tasks exist
        if blocked_by:
            for dep in blocked_by:
                if not self.exists(dep):
                    raise ValueError(f"Cannot create task: blocker {dep} does not exist")

        task = Task(
            id=self.next_id(),
            title=title,
            status=status,
            priority=priority,
            assignee=assignee,
            project=project,
            area=area,
            due=due,
            tags=tags or [],
            blocked_by=blocked_by or [],
            body=body,
        )
        self.save(task)
        return task

    def update(self, task_id: str, **updates) -> Task:
        task = self.get(task_id)
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        # Re-validate via __post_init__ semantics by recreating
        task = Task(**{**asdict(task), "body": task.body})
        if updates.get("status") == "Done" and not task.completed:
            task.completed = date.today().isoformat()
        self.save(task)
        return task
